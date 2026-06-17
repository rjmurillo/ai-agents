#!/usr/bin/env python3
"""Tests for the invoke_lsp_grep_guard PreToolUse hook (ADR-062).

Covers every decision path of the conditional LSP-first Grep guard:
  - positive (block): code symbol in Grep on a symbol-navigable code file with
    an available provider, default block mode.
  - negative (allow): non-code target, short pattern, no-symbol pattern, no
    provider configured, wrong tool, non-dict tool_input, missing pattern.
  - fail-open paths: tty stdin, empty stdin, malformed JSON, SKIP_LSP_GATE,
    consumer repo, any exception.
  - warn mode: LSP_GATE_MODE=warn emits an exit-0 advisory instead of blocking.
  - helper units: find_code_symbols, build_guidance, _select_target, _coerce_str.
  - entry points: module-as-script (subprocess feeding stdin) and runpy.

The block path is made deterministic by mocking detect_providers and
get_project_directory, so the suite does not depend on the host's Serena/MCP
configuration. One integration-style test exercises the real lib against a
``*.py`` glob to confirm the wiring.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(HOOK_DIR))

import invoke_lsp_grep_guard as guard  # noqa: E402

_HOOK_PATH = str(HOOK_DIR / "invoke_lsp_grep_guard.py")


def _grep_input(pattern: str, *, path: str = "", glob: str = "") -> str:
    """Build a Grep PreToolUse stdin payload."""
    tool_input: dict[str, str] = {"pattern": pattern}
    if path:
        tool_input["path"] = path
    if glob:
        tool_input["glob"] = glob
    return json.dumps({"tool_name": "Grep", "tool_input": tool_input})


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure env toggles do not leak between tests."""
    monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
    monkeypatch.delenv("LSP_DOWN", raising=False)
    monkeypatch.delenv("LSP_GATE_MODE", raising=False)


@pytest.fixture(autouse=True)
def _force_project_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Treat the test environment as the project repo by default.

    The guard short-circuits to allow in a consumer repo; default to project
    repo so the decision logic runs. Tests that exercise the consumer-repo
    skip override this explicitly.
    """
    monkeypatch.setattr(guard, "skip_if_consumer_repo", lambda _name: False)


# ---------------------------------------------------------------------------
# Unit tests: _coerce_str
# ---------------------------------------------------------------------------


class TestCoerceStr:
    def test_none_becomes_empty(self):
        assert guard._coerce_str(None) == ""

    def test_strips_whitespace(self):
        assert guard._coerce_str("  Foo  ") == "Foo"

    def test_non_string_coerced(self):
        assert guard._coerce_str(123) == "123"

    def test_list_coerced_does_not_raise(self):
        # Mirrors the kit's String() coercion: a non-string pattern does not
        # crash; it becomes a benign string.
        assert guard._coerce_str(["a", "b"]) == "['a', 'b']"


# ---------------------------------------------------------------------------
# Unit tests: _select_target
# ---------------------------------------------------------------------------


class TestSelectTarget:
    def test_prefers_glob_with_extension(self):
        assert guard._select_target("src/", "*.py") == "*.py"

    def test_falls_back_to_path_when_glob_has_no_extension(self):
        assert guard._select_target("src/foo.py", "src") == "src/foo.py"

    def test_empty_when_neither_scoped(self):
        assert guard._select_target("", "") == ""

    def test_path_used_when_glob_empty(self):
        assert guard._select_target("src/foo.py", "") == "src/foo.py"


# ---------------------------------------------------------------------------
# Unit tests: find_code_symbols
# ---------------------------------------------------------------------------


class TestFindCodeSymbols:
    def test_single_pascal_symbol(self):
        assert guard.find_code_symbols("SessionManager") == ["SessionManager"]

    def test_splits_on_pipe_keeps_symbols(self):
        result = guard.find_code_symbols("SessionManager|handleClick|foo")
        assert result == ["SessionManager", "handleClick"]

    def test_no_symbols_returns_empty(self):
        assert guard.find_code_symbols("foo|bar|baz") == []

    def test_trims_and_drops_empty_parts(self):
        assert guard.find_code_symbols(" SessionManager | ") == ["SessionManager"]

    def test_snake_case_function_symbol(self):
        assert guard.find_code_symbols("find_referencing_symbols") == ["find_referencing_symbols"]


# ---------------------------------------------------------------------------
# Unit tests: build_guidance
# ---------------------------------------------------------------------------


class TestBuildGuidance:
    def test_names_symbols_and_count(self):
        text = guard.build_guidance(["SessionManager"], ["serena"])
        assert "SessionManager" in text
        assert "1 code symbol(s)" in text

    def test_pascal_uses_definition_tool(self):
        text = guard.build_guidance(["SessionManager"], ["serena"])
        assert "find_symbol" in text

    def test_lowercase_uses_references_tool(self):
        text = guard.build_guidance(["handleClick"], ["serena"])
        assert "find_referencing_symbols" in text

    def test_includes_recovery_actions(self):
        text = guard.build_guidance(["SessionManager"], ["serena"])
        assert "activate_project" in text
        assert "initial_instructions" in text
        assert "SKIP_LSP_GATE" in text

    def test_native_lsp_provider_renders(self):
        text = guard.build_guidance(["SessionManager"], ["native_lsp"])
        assert "native LSP" in text

    def test_unknown_provider_key_skipped(self):
        # Defensive: an unexpected provider key does not crash; it is skipped.
        text = guard.build_guidance(["SessionManager"], ["bogus", "serena"])
        assert "find_symbol" in text

    def test_provider_without_tool_skipped(self, monkeypatch: pytest.MonkeyPatch):
        # Defensive: a registry entry that lacks the intent tool AND
        # symbol_search is skipped (exercises the empty-tool guard).
        toolless = {"label": "empty", "prefix": "mcp__empty__", "tools": {}}
        monkeypatch.setitem(guard.PROVIDERS, "empty", toolless)
        text = guard.build_guidance(["SessionManager"], ["empty", "serena"])
        assert "mcp__empty__" not in text
        assert "find_symbol" in text

    def test_no_dashes(self):
        text = guard.build_guidance(["SessionManager"], ["serena", "native_lsp"])
        assert chr(0x2014) not in text  # em dash
        assert chr(0x2013) not in text  # en dash


# ---------------------------------------------------------------------------
# main(): fail-open paths
# ---------------------------------------------------------------------------


class TestFailOpen:
    def test_tty_stdin_allows(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        assert guard.main() == 0

    def test_empty_stdin_allows(self, mock_stdin: Callable[[str], None]):
        mock_stdin("")
        assert guard.main() == 0

    def test_whitespace_stdin_allows(self, mock_stdin: Callable[[str], None]):
        mock_stdin("   \n  ")
        assert guard.main() == 0

    def test_malformed_json_allows(self, mock_stdin: Callable[[str], None]):
        mock_stdin("{not json")
        assert guard.main() == 0

    def test_wrong_tool_name_allows(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}))
        assert guard.main() == 0

    def test_non_dict_tool_input_allows(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Grep", "tool_input": "string"}))
        assert guard.main() == 0

    def test_missing_tool_input_allows(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Grep"}))
        assert guard.main() == 0

    def test_missing_pattern_allows(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Grep", "tool_input": {"glob": "*.py"}}))
        assert guard.main() == 0

    def test_short_pattern_allows(self, mock_stdin: Callable[[str], None]):
        mock_stdin(_grep_input("Foo", glob="*.py"))
        assert guard.main() == 0

    def test_no_symbol_pattern_allows(self, mock_stdin: Callable[[str], None]):
        mock_stdin(_grep_input("hello world stuff", glob="*.py"))
        assert guard.main() == 0

    def test_skip_lsp_gate_allows(
        self, mock_stdin: Callable[[str], None], monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("SKIP_LSP_GATE", "true")
        mock_stdin(_grep_input("SessionManager", glob="*.py"))
        assert guard.main() == 0

    def test_skip_lsp_gate_case_insensitive(
        self, mock_stdin: Callable[[str], None], monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("SKIP_LSP_GATE", "TRUE")
        mock_stdin(_grep_input("SessionManager", glob="*.py"))
        assert guard.main() == 0

    @patch("invoke_lsp_grep_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_grep_guard.detect_providers", return_value=["serena"])
    def test_lsp_down_allows_and_warns(
        self,
        _mock_detect,
        _mock_dir,
        mock_stdin: Callable[[str], None],
        monkeypatch: pytest.MonkeyPatch,
        capsys,
    ):
        monkeypatch.setenv("LSP_DOWN", "true")
        warn_once = MagicMock(return_value=True)
        monkeypatch.setattr(guard, "warn_once_lsp_down", warn_once)
        mock_stdin(_grep_input("SessionManager", glob="*.py"))
        assert guard.main() == 0
        warn_once.assert_called_once_with("lsp-grep-guard", "/project")
        assert capsys.readouterr().out == ""

    def test_consumer_repo_skips(
        self, mock_stdin: Callable[[str], None], monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(guard, "skip_if_consumer_repo", lambda _name: True)
        mock_stdin(_grep_input("SessionManager", glob="*.py"))
        assert guard.main() == 0

    def test_exception_fails_open(self, monkeypatch: pytest.MonkeyPatch):
        """An infrastructure error inside main() degrades to allow."""
        boom = MagicMock(isatty=MagicMock(side_effect=RuntimeError("boom")))
        monkeypatch.setattr("sys.stdin", boom)
        assert guard.main() == 0

    def test_non_code_target_allows(self, mock_stdin: Callable[[str], None]):
        # A markdown glob has no symbol_navigation capability: allow.
        mock_stdin(_grep_input("SessionManager", glob="*.md"))
        assert guard.main() == 0

    @patch("invoke_lsp_grep_guard.repo_programming_providers", return_value=[])
    def test_repo_wide_no_provider_allows(
        self, _mock_repo_providers, mock_stdin: Callable[[str], None]
    ):
        # No path, no glob -> repo-wide scope. With no active programming-language
        # provider, the repo probe returns False and the guard stays fail-open.
        mock_stdin(_grep_input("SessionManager"))
        assert guard.main() == 0

    @patch("invoke_lsp_grep_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_grep_guard.detect_providers", return_value=[])
    def test_no_provider_available_allows(
        self,
        _mock_detect,
        _mock_dir,
        mock_stdin: Callable[[str], None],
    ):
        # Code symbol + code target but no configured provider: fail-open.
        mock_stdin(_grep_input("SessionManager", glob="*.py"))
        assert guard.main() == 0


# ---------------------------------------------------------------------------
# main(): block path (positive)
# ---------------------------------------------------------------------------


class TestBlock:
    @patch("invoke_lsp_grep_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_grep_guard.detect_providers", return_value=["serena"])
    def test_blocks_pascal_symbol_on_py_glob(
        self,
        _mock_detect,
        _mock_dir,
        mock_stdin: Callable[[str], None],
        capsys,
    ):
        mock_stdin(_grep_input("SessionManager", glob="*.py"))
        assert guard.main() == 2
        captured = capsys.readouterr()
        assert "LSP-FIRST" in captured.out
        assert "find_symbol" in captured.out
        assert "blocked Grep" in captured.err

    @patch("invoke_lsp_grep_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_grep_guard.detect_providers", return_value=["serena"])
    def test_blocks_when_any_alternation_part_is_symbol(
        self,
        _mock_detect,
        _mock_dir,
        mock_stdin: Callable[[str], None],
        capsys,
    ):
        mock_stdin(_grep_input("foo|SessionManager|bar", glob="*.py"))
        assert guard.main() == 2
        captured = capsys.readouterr()
        assert "SessionManager" in captured.out
        assert "foo" not in captured.out.split("code symbol(s):")[1].split("\n")[0]

    @patch("invoke_lsp_grep_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_grep_guard.detect_providers", return_value=["serena"])
    def test_blocks_on_path_when_glob_absent(
        self,
        _mock_detect,
        _mock_dir,
        mock_stdin: Callable[[str], None],
    ):
        mock_stdin(_grep_input("find_referencing_symbols", path="src/lib.py"))
        assert guard.main() == 2


# ---------------------------------------------------------------------------
# Unit tests: _is_repo_wide_scope (directory / repo-wide detection, #2198)
# ---------------------------------------------------------------------------


class TestIsRepoWideScope:
    def test_empty_path_and_glob_is_repo_wide(self):
        assert guard._is_repo_wide_scope("", "") is True

    def test_extension_glob_is_not_repo_wide(self):
        # An explicit *.py / *.md glob scopes by file type; not a repo-wide scan.
        assert guard._is_repo_wide_scope("", "*.py") is False
        assert guard._is_repo_wide_scope("", "*.md") is False

    def test_in_repo_directory_is_repo_wide(self):
        # A real in-repo directory resolves and is a directory scope.
        assert guard._is_repo_wide_scope("scripts", "") is True

    def test_out_of_repo_path_is_not_repo_wide(self):
        # An out-of-repo absolute path must not be treated as in-repo scope.
        assert guard._is_repo_wide_scope("/tmp", "") is False

    def test_in_repo_file_is_not_directory_scope(self):
        # A path that names a file (not a directory) is handled by the per-target
        # check, not the repo-wide fallback.
        assert guard._is_repo_wide_scope("README.md", "") is False


# ---------------------------------------------------------------------------
# Unit tests: _resolve_in_repo
# ---------------------------------------------------------------------------


class TestResolveInRepo:
    def test_in_repo_relative_resolves(self):
        result = guard._resolve_in_repo("scripts")
        assert result is not None

    def test_out_of_repo_absolute_returns_none(self):
        assert guard._resolve_in_repo("/tmp/elsewhere") is None

    def test_parent_escape_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(guard, "get_project_directory", lambda: str(HOOK_DIR.parent))
        assert guard._resolve_in_repo("../../../../etc") is None


# ---------------------------------------------------------------------------
# main(): repo-wide / directory-scope gating (#2198)
# ---------------------------------------------------------------------------


class TestRepoWideGating:
    @patch("invoke_lsp_grep_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_grep_guard.repo_programming_providers", return_value=["serena"])
    @patch("invoke_lsp_grep_guard.detect_providers", return_value=["serena"])
    def test_repo_wide_blocks_when_provider_active(
        self,
        _mock_detect,
        _mock_repo_providers,
        _mock_dir,
        mock_stdin: Callable[[str], None],
        capsys,
    ):
        # (a) Repo-wide grep (no path, no glob) gates when a programming-language
        # provider is active. This is the #2198 bug: previously it allowed.
        mock_stdin(_grep_input("SessionManager"))
        assert guard.main() == 2
        captured = capsys.readouterr()
        assert "LSP-FIRST" in captured.out
        assert "find_symbol" in captured.out

    @patch("invoke_lsp_grep_guard.repo_programming_providers", return_value=["serena"])
    @patch("invoke_lsp_grep_guard.detect_providers", return_value=["serena"])
    def test_in_repo_directory_blocks_when_provider_active(
        self,
        _mock_detect,
        _mock_repo_providers,
        mock_stdin: Callable[[str], None],
    ):
        # A directory-scoped Grep (path is a real in-repo directory) also gates.
        # get_project_directory is left real so `scripts/` resolves on disk and
        # passes the is_dir() directory-scope check.
        repo_root = Path(__file__).resolve().parents[2]
        with patch("invoke_lsp_grep_guard.get_project_directory", return_value=str(repo_root)):
            mock_stdin(_grep_input("SessionManager", path="scripts"))
            assert guard.main() == 2

    @patch("invoke_lsp_grep_guard.repo_programming_providers", return_value=[])
    def test_out_of_repo_path_not_gated(
        self, _mock_repo_providers, mock_stdin: Callable[[str], None]
    ):
        # (b) An out-of-repo path is never gated. _is_repo_wide_scope returns
        # False for /tmp, so the repo probe is not even reached, but assert the
        # allow outcome directly.
        mock_stdin(_grep_input("SessionManager", path="/tmp"))
        assert guard.main() == 0

    @patch("invoke_lsp_grep_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_grep_guard.repo_programming_providers", return_value=[])
    def test_provider_less_repo_not_gated(
        self, _mock_repo_providers, _mock_dir, mock_stdin: Callable[[str], None]
    ):
        # (c) A provider-less repo: repo-wide grep stays fail-open.
        mock_stdin(_grep_input("SessionManager"))
        assert guard.main() == 0

    @patch("invoke_lsp_grep_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_grep_guard.repo_programming_providers", return_value=["serena"])
    def test_md_glob_not_gated_even_with_provider(
        self, _mock_repo_providers, _mock_dir, mock_stdin: Callable[[str], None]
    ):
        # A deliberate non-code glob (*.md) is not a repo-wide code scan; allow
        # even when a programming provider is active.
        mock_stdin(_grep_input("SessionManager", glob="*.md"))
        assert guard.main() == 0


# ---------------------------------------------------------------------------
# main(): warn mode (LSP_GATE_MODE=warn)
# ---------------------------------------------------------------------------


class TestWarnMode:
    @patch("invoke_lsp_grep_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_grep_guard.detect_providers", return_value=["serena"])
    def test_warn_mode_allows_with_advisory(
        self,
        _mock_detect,
        _mock_dir,
        mock_stdin: Callable[[str], None],
        monkeypatch: pytest.MonkeyPatch,
        capsys,
    ):
        monkeypatch.setenv("LSP_GATE_MODE", "warn")
        mock_stdin(_grep_input("SessionManager", glob="*.py"))
        assert guard.main() == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert "LSP-FIRST" in payload["systemMessage"]
        assert "warn mode" in captured.err

    @patch("invoke_lsp_grep_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_grep_guard.detect_providers", return_value=["serena"])
    def test_block_mode_default_blocks(
        self,
        _mock_detect,
        _mock_dir,
        mock_stdin: Callable[[str], None],
        monkeypatch: pytest.MonkeyPatch,
    ):
        # Explicit block mode (and unknown values) keep the exit-2 behavior.
        monkeypatch.setenv("LSP_GATE_MODE", "block")
        mock_stdin(_grep_input("SessionManager", glob="*.py"))
        assert guard.main() == 2


# ---------------------------------------------------------------------------
# Integration: real lib wiring against this repo's config
# ---------------------------------------------------------------------------


class TestRealLibWiring:
    def test_real_detect_providers_blocks_py_glob(self, mock_stdin: Callable[[str], None]):
        """Without mocking the lib, a code symbol on *.py blocks in this repo.

        This repo configures python in .serena/project.yml and registers the
        serena MCP server, so detect_providers returns a non-empty list and the
        guard blocks. Confirms the bootstrap import and wiring are correct.
        """
        mock_stdin(_grep_input("SessionManager", glob="*.py"))
        assert guard.main() == 2


# ---------------------------------------------------------------------------
# Entry points: module-as-script and runpy
# ---------------------------------------------------------------------------


class TestModuleAsScript:
    def test_runs_as_subprocess_allows_non_grep(self):
        import subprocess

        result = subprocess.run(
            ["python3", _HOOK_PATH],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_runs_as_subprocess_blocks_symbol(self):
        import subprocess

        result = subprocess.run(
            ["python3", _HOOK_PATH],
            input=_grep_input("SessionManager", glob="*.py"),
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        assert result.returncode == 2
        assert "LSP-FIRST" in result.stdout

    def test_main_guard_via_runpy(self, monkeypatch: pytest.MonkeyPatch):
        """Cover the sys.exit(main()) line via runpy in-process execution."""
        import runpy

        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {}})),
        )
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(_HOOK_PATH, run_name="__main__")
        assert exc_info.value.code == 0
