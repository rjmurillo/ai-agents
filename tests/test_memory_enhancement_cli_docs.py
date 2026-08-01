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

Two limits are deliberate, because closing either one costs more than it
returns:

1. It checks invocations, not bare nouns. A backticked command name in prose,
   such as "run `add-citation`", carries no argv and is not flagged. A lexical
   detector for bare names was measured before being rejected: 1626 candidate
   spans repo-wide, and 118 even when scoped to the files that document this
   CLI. Every sampled candidate was a legitimate field name, source type, link
   type, or JSON key, and there is no lexical signal separating those from a
   phantom subcommand. All ten current mentions of the phantom commands are
   negative prose ("there is no `add-citation` command") that such a detector
   would flag as errors.
2. It checks syntax, not semantics. A prose claim about behavior, such as a
   wrong default or a capability the CLI does not have, parses as valid
   English and never reaches argparse. Three such errors survived this guard
   and were caught only by review. Verify behavioral claims against a run.
"""

from __future__ import annotations

import contextlib
import io
import re
import shlex
import subprocess
from pathlib import Path

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
# Shell control operators end the command being documented.
_OPERATORS = frozenset({"&&", "||", "|", ";", "&"})
# Redirections consume the token that follows them. The descriptor-duplicating
# forms carry a leading file-descriptor number, which is shell syntax and not
# an argument.
_REDIRECTS = frozenset({">", ">>", "<", "<<", ">&", "<&", "&>", ">>&"})
# Options parsed with type=int. A synopsis writes their value as a
# metavariable, which argparse rejects before it can check the option name,
# so substitute a concrete integer to keep the name under test.
_INT_OPTIONS = frozenset({"--depth", "--top"})
# Emitted when a fragment cannot be tokenized. It fails argparse, so the
# invocation test reports the file and line instead of dropping it silently.
_UNPARSEABLE = "<<unparseable>>"

VALID_SUBCOMMANDS = frozenset(
    {"verify", "verify-all", "health", "graph", "confidence", "search"}
)

# Global options that consume the token after them, which must not be mistaken
# for a subcommand name.
_VALUE_TAKING_GLOBALS = frozenset({"--repo-root", "--memories-dir"})

# Enough documented invocations must be found that a broken scanner cannot
# pass this suite by silently matching nothing.
MINIMUM_INVOCATIONS = 40


def _substitute_int_values(tokens: list[str]) -> list[str]:
    """Give int-typed options a parseable value so the option name is checked."""
    substituted: list[str] = []
    expects_int = False
    for token in tokens:
        if expects_int:
            expects_int = False
            if token.lstrip("-").isdigit():
                substituted.append(token)
                continue
            substituted.append("1")
            # A metavariable is the option's value and is now consumed. A flag
            # is not, and must stay visible or a phantom option name written
            # after a bare --depth would vanish instead of failing argparse.
            if not token.startswith("-"):
                continue
        option, separator, value = token.partition("=")
        if option in _INT_OPTIONS:
            if not separator:
                expects_int = True
            elif not value.lstrip("-").isdigit():
                token = f"{option}=1"
        substituted.append(token)
    return substituted


def _prepare(fragment: str) -> str:
    """Strip synopsis conventions that are not shell syntax."""
    fragment = fragment.split("`", 1)[0]
    # Placeholders resolve before tokenization: the '>' closing '<id>'
    # otherwise reads as a redirect and swallows the token after it.
    fragment = _PLACEHOLDER.sub(_PLACEHOLDER_TOKEN, fragment)
    fragment = _OPTIONAL.sub(r"\1", fragment)
    return fragment.strip().removesuffix("\\").strip()


def _shell_argv(tokens: list[str]) -> list[str]:
    """Truncate at the first control operator and drop redirection targets."""
    argv: list[str] = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token in _OPERATORS:
            break
        if token in _REDIRECTS:
            # `2> err.txt` tokenizes the descriptor apart from the operator.
            # Without this the stray 2 survives as a positional argument and
            # the guard rejects a valid documented command.
            if argv and argv[-1].isdigit():
                argv.pop()
            skip_next = True
            continue
        argv.append(token)
    return argv


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
        encoding="utf-8",
        errors="replace",
        check=True,
        cwd=REPO_ROOT,
    )
    return listing.stdout.split()


def _argv_from(fragment: str) -> list[str]:
    """Normalize a documented fragment into argv.

    Tokenization runs before shell semantics are applied, so a quoted
    metacharacter stays inside its token instead of truncating the command.
    """
    lexer = shlex.shlex(_prepare(fragment), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return [_UNPARSEABLE]
    return _substitute_int_values(_shell_argv(tokens))


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


def _continues(line: str) -> bool:
    """Report whether a shell line continues onto the next one."""
    stripped = line.rstrip()
    return stripped.endswith("\\") and not stripped.endswith("\\\\")


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
        pending = ""
        pending_number = 0
        for number, line in enumerate(text.splitlines(), start=1):
            fence_language, is_fence = _fence_language_after(line, fence_language)
            if is_fence:
                pending = ""
                continue
            runnable = fence_language in _SHELL_FENCE_LANGUAGES
            if pending:
                line = f"{pending} {line.strip()}"
            else:
                pending_number = number
            # A trailing backslash continues the command only inside a shell
            # fence. In prose it is a Markdown hard line break.
            if runnable and _continues(line):
                pending = line.rstrip().removesuffix("\\").rstrip()
                continue
            pending = ""
            for argv, in_shell in _line_invocations(line, runnable):
                collected.append(
                    (relative_path, pending_number, line.strip(), argv, in_shell)
                )
    return collected


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

    def test_every_doc_root_contributes_invocations(self) -> None:
        """Deleting a root must fail loudly instead of quietly shrinking scope.

        Checking only that each configured root exists is vacuous: removing a
        root from DOC_ROOTS also removes it from the assertion. Pinning the
        expected set closes that. The count floor alone is no defence either,
        because the two mirror roots supply most of the matches on their own.
        """
        assert set(DOC_ROOTS) == {
            ".claude/skills",
            ".claude/rules",
            "src/copilot-cli/skills",
            "src/copilot-cli/instructions",
            ".agents/architecture",
            ".agents/guides",
            ".serena/memories",
        }, "DOC_ROOTS changed; confirm the new scope is intended"
        by_root = {root: 0 for root in DOC_ROOTS}
        for relative_path in _tracked_docs():
            for root in DOC_ROOTS:
                if relative_path.startswith(f"{root}/"):
                    by_root[root] += 1
        empty = sorted(root for root in DOC_ROOTS if by_root[root] == 0)
        assert not empty, f"pinned doc roots with no tracked files: {empty}"

        by_root = {root: 0 for root in DOC_ROOTS}
        for relative_path, *_ in documented_invocations():
            for root in DOC_ROOTS:
                if relative_path.startswith(f"{root}/"):
                    by_root[root] += 1
        # The two instruction roots are watched for future drift; today their
        # only mention of the module is prose about a tracked symlink. They are
        # exempt from contributing invocations, not from existing: the file
        # census above still fails if either is emptied. The rest carry real
        # invocations and must not fall silent.
        documenting = set(DOC_ROOTS) - {".claude/rules", "src/copilot-cli/instructions"}
        silent = sorted(root for root in documenting if by_root[root] == 0)
        assert not silent, f"doc roots contributing no invocations: {silent}"

    def test_all_documented_invocations_parse(self) -> None:
        failures = []
        for relative_path, number, raw, argv, runnable in documented_invocations():
            error = invocation_error(argv, runnable)
            if error is not None:
                failures.append(f"{relative_path}:{number}\n    {raw}\n    {error}")
        assert not failures, "documented commands the CLI rejects:\n" + "\n".join(
            failures
        )
