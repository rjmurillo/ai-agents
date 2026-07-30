"""Guard that documented `memory_enhancement` invocations match the real CLI.

The memory-enhancement skill was authored against a planned command surface
that was never fully implemented. Agents following the docs ran commands that
exit 2. This module parses every documented invocation with the shipping
argparse tree, so a doc that advertises a command or flag the CLI does not
have fails here instead of failing an agent at runtime.

Scope: live instruction surfaces only. Session logs, archives, critiques, and
PRDs record what was proposed or done at the time and are deliberately not
rewritten to match today's code. Workflow invocations are covered separately
by tests/ci/test_parse_memory_health_results.py.

Doc convention this enforces: `<placeholder>` marks a value the reader
substitutes, and `[optional]` marks an optional argument. Both are unwrapped
before parsing, so an optional flag that does not exist still fails.
"""

from __future__ import annotations

import contextlib
import io
import re
import shlex
import subprocess
from pathlib import Path

import pytest

from memory_enhancement.__main__ import _build_parser

REPO_ROOT = Path(__file__).resolve().parents[1]

# Documentation that instructs an agent today. Historical records are excluded.
DOC_ROOTS = (
    ".claude/skills",
    ".claude/rules",
    "src/copilot-cli/skills",
    "src/copilot-cli/instructions",
    ".agents/architecture",
    ".agents/guides",
    ".serena/memories",
)

_REDIRECT = re.compile(r"\d?>>?\s*\S+")
_SEPARATOR = re.compile(r"&&|\|\||[|;]")
_INVOCATION = re.compile(r"-m\s+(?:scripts\.)?memory_enhancement(.*)")
# Inline-code spans that name a subcommand and an option without the module
# prefix, such as `graph --start <id> [--depth N]` in prose. These carry the
# same phantom-flag risk as a full command line.
_BARE_INVOCATION = re.compile(
    r"`((?:verify-all|verify|health|graph|confidence|search)\b[^`]*--[^`]*)`"
)
_PLACEHOLDER = re.compile(r"<[^>]*>")
_OPTIONAL = re.compile(r"\[([^\]]*)\]")
_FENCE = re.compile(r"^\s*```+\s*(\w*)")
_SHELL_FENCE_LANGUAGES = frozenset({"bash", "sh", "shell", "console"})
_PLACEHOLDER_TOKEN = "PLACEHOLDER"
# Options parsed with type=int. A synopsis writes their value as a
# metavariable, which argparse rejects before it can check the option name,
# so substitute a concrete integer to keep the name under test.
_INT_VALUE_OPTION = re.compile(r"(--depth|--top)(\s+)(\S+)")

VALID_SUBCOMMANDS = frozenset(
    {"verify", "verify-all", "health", "graph", "confidence", "search"}
)

# Global options that consume the token after them, which must not be mistaken
# for a subcommand name.
_VALUE_TAKING_GLOBALS = frozenset({"--repo-root", "--memories-dir"})

# Enough documented invocations must be found that a broken scanner cannot
# pass this suite by silently matching nothing.
MINIMUM_INVOCATIONS = 40


def _substitute_int_values(fragment: str) -> str:
    """Give int-typed options a parseable value so the option name is checked."""

    def replace(match: re.Match[str]) -> str:
        option, gap, value = match.group(1), match.group(2), match.group(3)
        if value.lstrip("-").isdigit():
            return match.group(0)
        return f"{option}{gap}1"

    return _INT_VALUE_OPTION.sub(replace, fragment)


def _normalize(fragment: str) -> str:
    """Reduce a documented command fragment to the argv it advertises."""
    fragment = fragment.split("`", 1)[0]
    # Placeholders resolve first: the '>' closing '<id>' otherwise looks like a
    # shell redirect and swallows the token after it.
    fragment = _PLACEHOLDER.sub(_PLACEHOLDER_TOKEN, fragment)
    fragment = _REDIRECT.sub(" ", fragment)
    fragment = _SEPARATOR.split(fragment, 1)[0]
    fragment = _OPTIONAL.sub(r"\1", fragment)
    fragment = _substitute_int_values(fragment)
    return fragment.replace("\\", " ").strip()


def parse_error(argv: list[str]) -> str | None:
    """Return the argparse error for argv, or None when argv is valid."""
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(
            io.StringIO()
        ):
            _build_parser().parse_args(argv)
    except SystemExit as exit_signal:
        if exit_signal.code:
            return (stderr.getvalue().strip().splitlines() or ["unknown error"])[-1]
    return None


def _subcommand_index(argv: list[str]) -> int | None:
    """Return the index of the subcommand position, skipping global options."""
    index = 0
    while index < len(argv):
        token = argv[index]
        if not token.startswith("-"):
            return index
        if token in _VALUE_TAKING_GLOBALS:
            index += 1
        index += 1
    return None


def invocation_error(argv: list[str], runnable: bool) -> str | None:
    """Return the defect in a documented invocation, or None when it is sound.

    Inside a shell fence the line is a command a reader copies, so the whole
    argv must parse. Outside a fence, prose and reference tables legitimately
    name a command without its arguments, and a synopsis puts a placeholder in
    the subcommand position. Those two shapes are exempt; everything else in
    prose still gets a full parse, so a phantom flag in a sentence is caught.
    """
    if runnable:
        return parse_error(argv)
    index = _subcommand_index(argv)
    if index is None or argv[index] == _PLACEHOLDER_TOKEN:
        return None
    if argv[index] in VALID_SUBCOMMANDS and not argv[index + 1 :]:
        return None
    return parse_error(argv)


def _tracked_docs() -> list[str]:
    listing = subprocess.run(
        ["git", "ls-files", "--", *DOC_ROOTS],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    return listing.stdout.split()


def _argv_from(fragment: str) -> list[str]:
    """Normalize a documented fragment into argv, or an empty list."""
    try:
        return shlex.split(_normalize(fragment))
    except ValueError:
        return []


def _line_invocations(line: str, runnable: bool) -> list[tuple[list[str], bool]]:
    """Return the argv advertised by one documented line.

    A full ``-m memory_enhancement`` command line inherits its fence context. A
    bare subcommand fragment in inline code is always prose.
    """
    match = _INVOCATION.search(line)
    if match is not None:
        argv = _argv_from(match.group(1))
        return [(argv, runnable)] if argv else []
    found: list[tuple[list[str], bool]] = []
    for bare in _BARE_INVOCATION.finditer(line):
        argv = _argv_from(bare.group(1))
        if argv:
            found.append((argv, False))
    return found


def _fence_language_after(line: str, current: str | None) -> tuple[str | None, bool]:
    """Track fenced-block state; the bool reports whether the line was a fence."""
    fence = _FENCE.match(line)
    if fence is None:
        return current, False
    return (None if current is not None else fence.group(1)), True


def documented_invocations() -> list[tuple[str, int, str, list[str], bool]]:
    """Collect invocations as (path, line, raw, argv, inside_shell_fence)."""
    collected: list[tuple[str, int, str, list[str], bool]] = []
    for relative_path in _tracked_docs():
        try:
            text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "memory_enhancement" not in text:
            continue
        fence_language: str | None = None
        for number, line in enumerate(text.splitlines(), start=1):
            fence_language, is_fence = _fence_language_after(line, fence_language)
            if is_fence:
                continue
            runnable = fence_language in _SHELL_FENCE_LANGUAGES
            for argv, in_shell in _line_invocations(line, runnable):
                collected.append((relative_path, number, line.strip(), argv, in_shell))
    return collected


class TestDetector:
    """The scanner must catch bad invocations and clear good ones."""

    @pytest.mark.parametrize(
        ("argv", "expected"),
        [
            (["add-citation", "PLACEHOLDER"], "invalid choice"),
            (["update-confidence", "PLACEHOLDER"], "invalid choice"),
            (["list-citations", "PLACEHOLDER"], "invalid choice"),
            (["health", "--format", "json"], "unrecognized"),
            (["health", "--summary"], "unrecognized"),
            (["health", "--include-graph"], "unrecognized"),
            (["verify-all", "--repo-root", "."], "unrecognized"),
            (["verify", "PLACEHOLDER"], "unrecognized"),
            (["verify-all", "--dir", ".serena/memories"], "unrecognized"),
            (["graph", "PLACEHOLDER"], "required"),
        ],
    )
    def test_rejects_known_bad(self, argv: list[str], expected: str) -> None:
        error = parse_error(argv)
        assert error is not None, f"{argv} should not parse"
        assert expected in error, f"{argv} -> {error}"

    @pytest.mark.parametrize(
        "argv",
        [
            ["health"],
            ["health", "--json"],
            ["health", "--markdown"],
            ["health", "--text"],
            ["--repo-root", ".", "health", "--json"],
            ["--memories-dir", ".serena/memories", "verify-all"],
            ["verify"],
            ["verify", "--memory-id", "PLACEHOLDER"],
            ["verify-all", "--json"],
            ["graph", "--start", "PLACEHOLDER"],
            ["graph", "--start", "PLACEHOLDER", "--depth", "2"],
            ["confidence"],
            ["search", "PLACEHOLDER"],
            ["search", "PLACEHOLDER", "--top", "5", "--json"],
        ],
    )
    def test_accepts_known_good(self, argv: list[str]) -> None:
        assert parse_error(argv) is None, f"{argv} should parse"

    def test_normalize_unwraps_optional_and_placeholder(self) -> None:
        assert _normalize(" health [--json]") == "health --json"
        assert _normalize(" verify --memory-id <id>") == "verify --memory-id PLACEHOLDER"
        assert _normalize(" health --json > out.json") == "health --json"

    def test_normalize_keeps_unknown_optional_flags_visible(self) -> None:
        """Unwrapping must not let a nonexistent optional flag through."""
        argv = shlex.split(_normalize(" verify-all [--dir PATH]"))
        assert parse_error(argv) is not None

    def test_normalize_substitutes_int_metavariables(self) -> None:
        """A synopsis value for an int option must not mask the option name."""
        assert _normalize(" graph --start <id> [--depth N]") == (
            "graph --start PLACEHOLDER --depth 1"
        )
        assert _normalize(" search q --top <n>") == "search q --top 1"

    def test_normalize_preserves_real_integers(self) -> None:
        assert _normalize(" graph --start x --depth 3") == "graph --start x --depth 3"

    def test_normalize_does_not_treat_placeholder_close_as_redirect(self) -> None:
        """'<id>' must not swallow the token after it the way '> file' does."""
        assert _normalize(" verify --memory-id <id> --json") == (
            "verify --memory-id PLACEHOLDER --json"
        )
        assert _normalize(" health --json > out.json") == "health --json"

    def test_int_substitution_does_not_excuse_a_phantom_flag(self) -> None:
        """Substitution applies to the value, never to the option name."""
        argv = shlex.split(_normalize(" graph --start <id> [--max-depth N]"))
        assert parse_error(argv) is not None

    @pytest.mark.parametrize(
        "line",
        [
            "prose mentioning `graph --start <id> --strategy dfs` inline",
            "the `health --format json` form",
            "call `verify-all --dir .serena/memories` first",
        ],
    )
    def test_bare_invocation_regex_catches_phantom_flags(self, line: str) -> None:
        """A subcommand fragment without the module prefix is still checked."""
        match = _BARE_INVOCATION.search(line)
        assert match is not None
        argv = shlex.split(_normalize(match.group(1)))
        assert invocation_error(argv, runnable=False) is not None

    @pytest.mark.parametrize(
        "line",
        [
            "the `verify` subcommand",
            "run `health` to see the report",
            "`graph` traverses links",
        ],
    )
    def test_bare_invocation_regex_ignores_flagless_names(self, line: str) -> None:
        """Reference-table rows naming a subcommand must not be swept in."""
        assert _BARE_INVOCATION.search(line) is None

    def test_bare_invocation_regex_accepts_real_fragments(self) -> None:
        match = _BARE_INVOCATION.search("run `graph --start <id> [--depth N]` next")
        assert match is not None
        argv = shlex.split(_normalize(match.group(1)))
        assert invocation_error(argv, runnable=False) is None

    @pytest.mark.parametrize(
        "argv",
        [
            ["add-citation"],
            ["update-confidence"],
            ["list-citations"],
            ["auto-cite"],
            ["doctor"],
        ],
    )
    def test_prose_mode_rejects_phantom_names(self, argv: list[str]) -> None:
        assert invocation_error(argv, runnable=False) is not None

    @pytest.mark.parametrize(
        "argv",
        [
            ["graph"],
            ["search"],
            ["verify"],
            [_PLACEHOLDER_TOKEN],
            ["--repo-root", "PATH", "--memories-dir", "PATH", _PLACEHOLDER_TOKEN],
            ["--repo-root", "PATH", "health"],
        ],
    )
    def test_prose_mode_allows_bare_names_and_synopses(self, argv: list[str]) -> None:
        """Tables name a command; a synopsis leaves the command a placeholder."""
        assert invocation_error(argv, runnable=False) is None

    def test_prose_mode_reads_past_global_option_values(self) -> None:
        """A global option's value must not be read as the subcommand name."""
        assert invocation_error(["--repo-root", "PATH", "add-citation"], False)

    @pytest.mark.parametrize(
        "argv",
        [
            ["graph", _PLACEHOLDER_TOKEN, "--strategy", "dfs"],
            ["graph", _PLACEHOLDER_TOKEN, "--max-depth", "3"],
            ["verify", _PLACEHOLDER_TOKEN],
            ["health", "--format", "json"],
        ],
    )
    def test_prose_mode_still_checks_arguments_when_present(
        self, argv: list[str]
    ) -> None:
        """Exempting bare names must not exempt a real invocation in prose."""
        assert invocation_error(argv, runnable=False) is not None

    def test_fenced_mode_checks_incomplete_commands(self) -> None:
        """A fenced line is copy-pasted, so a missing required flag is a defect."""
        assert invocation_error(["graph"], runnable=True) is not None
        assert invocation_error(["graph"], runnable=False) is None


class TestDocumentedInvocations:
    """Every documented invocation must parse against the shipping CLI."""

    def test_scan_is_not_vacuous(self) -> None:
        found = documented_invocations()
        assert len(found) >= MINIMUM_INVOCATIONS, (
            f"only {len(found)} invocations found across {DOC_ROOTS}; "
            "the scanner or the doc roots are broken"
        )

    def test_scan_finds_both_fenced_and_prose_invocations(self) -> None:
        """Both checking modes must have real coverage, not just one."""
        found = documented_invocations()
        fenced = [row for row in found if row[4]]
        prose = [row for row in found if not row[4]]
        assert fenced, "no invocation found inside a shell code fence"
        assert prose, "no invocation found outside a shell code fence"

    def test_doc_roots_are_all_populated(self) -> None:
        """A renamed root must fail loudly instead of shrinking coverage."""
        empty = [root for root in DOC_ROOTS if not (REPO_ROOT / root).is_dir()]
        assert not empty, f"doc roots missing: {empty}"

    def test_all_documented_invocations_parse(self) -> None:
        failures = []
        for relative_path, number, raw, argv, runnable in documented_invocations():
            error = invocation_error(argv, runnable)
            if error is not None:
                failures.append(f"{relative_path}:{number}\n    {raw}\n    {error}")
        assert not failures, "documented commands the CLI rejects:\n" + "\n".join(
            failures
        )
