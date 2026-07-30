"""Self-tests for the documented-invocation scanner.

The scanner in test_memory_enhancement_cli_docs.py is the instrument that
decides whether the shipped documentation is correct. An instrument that
silently matches nothing, or that mangles a fragment before parsing it, would
report a clean corpus while the docs rot. These tests hold the instrument to
its contract: known-bad invocations must fail, known-good ones must pass, and
the shell-fragment normalizer must preserve meaning.

The corpus scan itself lives in the sibling module.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import tests.test_memory_enhancement_cli_docs as docs
from tests.test_memory_enhancement_cli_docs import (
    _BARE_INVOCATION,
    _PLACEHOLDER_TOKEN,
    _UNPARSEABLE,
    _argv_from,
    invocation_error,
    parse_error,
)


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

    def test_argv_unwraps_optional_and_placeholder(self) -> None:
        assert _argv_from(" health [--json]") == ["health", "--json"]
        assert _argv_from(" verify --memory-id <id>") == [
            "verify",
            "--memory-id",
            "PLACEHOLDER",
        ]
        assert _argv_from(" health --json > out.json") == ["health", "--json"]

    def test_argv_keeps_unknown_optional_flags_visible(self) -> None:
        """Unwrapping must not let a nonexistent optional flag through."""
        assert parse_error(_argv_from(" verify-all [--dir PATH]")) is not None

    def test_argv_substitutes_int_metavariables(self) -> None:
        """A synopsis value for an int option must not mask the option name."""
        assert _argv_from(" graph --start <id> [--depth N]") == [
            "graph",
            "--start",
            "PLACEHOLDER",
            "--depth",
            "1",
        ]
        assert _argv_from(" search q --top <n>") == ["search", "q", "--top", "1"]

    def test_argv_substitutes_equals_form_int_values(self) -> None:
        """The '--depth=<N>' spelling must be substituted like the spaced form."""
        assert _argv_from(" graph --start x --depth=<N>") == [
            "graph",
            "--start",
            "x",
            "--depth=1",
        ]
        assert parse_error(_argv_from(" graph --start x --depth=<N>")) is None

    def test_argv_preserves_real_integers(self) -> None:
        assert _argv_from(" graph --start x --depth 3") == [
            "graph",
            "--start",
            "x",
            "--depth",
            "3",
        ]

    def test_argv_does_not_treat_placeholder_close_as_redirect(self) -> None:
        """'<id>' must not swallow the token after it the way '> file' does."""
        assert _argv_from(" verify --memory-id <id> --json") == [
            "verify",
            "--memory-id",
            "PLACEHOLDER",
            "--json",
        ]

    def test_quoted_metacharacter_does_not_truncate_the_command(self) -> None:
        """A pipe inside quotes is data, so the flag after it stays under test."""
        assert _argv_from(' search "a|b" --bogus') == ["search", "a|b", "--bogus"]
        assert parse_error(_argv_from(' search "a|b" --bogus')) is not None

    def test_unquoted_operator_truncates_the_command(self) -> None:
        assert _argv_from(" health --json | jq .") == ["health", "--json"]
        assert _argv_from(" health --json|jq") == ["health", "--json"]
        assert _argv_from(" verify && health") == ["verify"]

    def test_trailing_comment_is_stripped(self) -> None:
        assert _argv_from(" health --json  # writes the report") == [
            "health",
            "--json",
        ]

    def test_unbalanced_quote_is_reported_not_dropped(self) -> None:
        """An untokenizable fragment must fail loudly, naming its line."""
        argv = _argv_from(' search "unclosed --json')
        assert argv == [_UNPARSEABLE]
        assert parse_error(argv) is not None

    def test_int_substitution_does_not_excuse_a_phantom_flag(self) -> None:
        """Substitution applies to the value, never to the option name."""
        argv = _argv_from(" graph --start <id> [--max-depth N]")
        assert parse_error(argv) is not None

    @pytest.mark.parametrize(
        "fragment",
        [
            " graph --start x --depth --bogus",
            " search query --top --bogus",
        ],
    )
    def test_int_substitution_does_not_swallow_a_following_flag(
        self, fragment: str
    ) -> None:
        """A flag after a bare int option is not that option's value.

        Consuming it hid a phantom flag from argparse entirely, which is the
        one thing this guard exists to catch.
        """
        argv = _argv_from(fragment)
        assert "--bogus" in argv
        assert parse_error(argv) is not None

    @pytest.mark.parametrize(
        "fragment",
        [
            " health --json 2> err.txt",
            " health --json 2>&1",
            " health --json > out.txt",
        ],
    )
    def test_redirections_leave_no_stray_descriptor(self, fragment: str) -> None:
        """A file-descriptor prefix is shell syntax, not a positional."""
        assert _argv_from(fragment) == ["health", "--json"]

    def test_quoted_command_substitution_stays_one_token(self) -> None:
        """The shipped verify-all example quotes a $(...) repo root."""
        argv = _argv_from(' --repo-root "$(git rev-parse --show-toplevel)" verify-all')
        assert argv == [
            "--repo-root",
            "$(git rev-parse --show-toplevel)",
            "verify-all",
        ]
        assert parse_error(argv) is None

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
        assert invocation_error(_argv_from(match.group(1)), runnable=False) is not None

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
        assert invocation_error(_argv_from(match.group(1)), runnable=False) is None

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


class TestLineContinuation:
    """A command split across lines must be scanned as one invocation."""

    @staticmethod
    def _scan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str) -> list:
        (tmp_path / "doc.md").write_text(body, encoding="utf-8")
        monkeypatch.setattr(docs, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(docs, "_tracked_docs", lambda: ["doc.md"])
        return docs.documented_invocations()

    def test_shell_fence_joins_continued_lines(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Without joining, a phantom flag on the second line is never seen."""
        rows = self._scan(
            monkeypatch,
            tmp_path,
            "```bash\npython -m memory_enhancement graph --start id \\\n"
            "  --bogus\n```\n",
        )
        assert len(rows) == 1
        _, number, _, argv, runnable = rows[0]
        assert argv == ["graph", "--start", "id", "--bogus"]
        assert number == 2, "the invocation is attributed to the line it starts on"
        assert docs.invocation_error(argv, runnable) is not None

    def test_prose_backslash_is_a_markdown_break_not_a_continuation(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Outside a shell fence a trailing backslash joins nothing."""
        rows = self._scan(
            monkeypatch,
            tmp_path,
            "About memory_enhancement, note this break \\\n"
            "See `health --json` for details.\n",
        )
        assert [(row[1], row[3]) for row in rows] == [(2, ["health", "--json"])]
