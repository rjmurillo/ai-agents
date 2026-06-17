#!/usr/bin/env python3
"""Tests for the invoke_lsp_glob_guard PreToolUse hook (ADR-062).

Covers every decision path of the conditional LSP-first Glob guard:
  - positive (block): symbol-shaped glob token with an available provider
    (extension-scoped and bare-symbol cases), default block mode.
  - negative (allow): extension-only glob, lowercase concept glob, non-code
    extension with a symbol token, no provider configured, wrong tool, non-dict
    tool_input, missing/empty pattern.
  - fail-open paths: tty stdin, empty stdin, malformed JSON, SKIP_LSP_GATE,
    consumer repo, any exception.
  - warn mode: LSP_GATE_MODE=warn emits an exit-0 advisory instead of blocking.
  - helper units: find_glob_symbols, glob_extension, resolve_providers,
    build_guidance, _coerce_str.
  - entry points: module-as-script (subprocess feeding stdin) and runpy.

The block path is made deterministic by mocking detect_providers and
get_project_directory, so the suite does not depend on the host's Serena/MCP
configuration. One integration-style test exercises the real lib against a bare
symbol glob to confirm the wiring.
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

import invoke_lsp_glob_guard as guard  # noqa: E402

_HOOK_PATH = str(HOOK_DIR / "invoke_lsp_glob_guard.py")


def _glob_input(pattern: str) -> str:
    """Build a Glob PreToolUse stdin payload."""
    return json.dumps({"tool_name": "Glob", "tool_input": {"pattern": pattern}})


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure env toggles do not leak between tests."""
    monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
    monkeypatch.delenv("LSP_DOWN", raising=False)
    monkeypatch.delenv("LSP_GATE_MODE", raising=False)


@pytest.fixture(autouse=True)
def _force_project_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Treat the test environment as the project repo by default."""
    monkeypatch.setattr(guard, "skip_if_consumer_repo", lambda _name: False)


# ---------------------------------------------------------------------------
# Unit tests: _coerce_str
# ---------------------------------------------------------------------------


class TestCoerceStr:
    def test_none_becomes_empty(self):
        assert guard._coerce_str(None) == ""

    def test_strips_whitespace(self):
        assert guard._coerce_str("  *Foo*  ") == "*Foo*"

    def test_non_string_coerced(self):
        assert guard._coerce_str(123) == "123"

    def test_list_coerced_does_not_raise(self):
        assert guard._coerce_str(["a", "b"]) == "['a', 'b']"


# ---------------------------------------------------------------------------
# Unit tests: glob_extension
# ---------------------------------------------------------------------------


class TestGlobExtension:
    def test_trailing_extension(self):
        assert guard.glob_extension("*UserService*.ts") == ".ts"

    def test_double_star_extension(self):
        assert guard.glob_extension("**/*.json") == ".json"

    def test_bare_symbol_has_no_extension(self):
        assert guard.glob_extension("*UserService*") == ""

    def test_directory_glob_has_no_extension(self):
        assert guard.glob_extension("src/**") == ""


# ---------------------------------------------------------------------------
# Unit tests: find_glob_symbols
# ---------------------------------------------------------------------------


class TestFindGlobSymbols:
    def test_pascal_symbol_token(self):
        assert guard.find_glob_symbols("*UserService*") == ["UserService"]

    def test_pascal_symbol_with_extension(self):
        assert guard.find_glob_symbols("**/AuthProvider.tsx") == ["AuthProvider"]

    def test_camel_symbol_token(self):
        assert guard.find_glob_symbols("*createOrder*") == ["createOrder"]

    def test_snake_function_token(self):
        assert guard.find_glob_symbols("*get_user_sessions*") == ["get_user_sessions"]

    def test_extension_only_has_no_symbols(self):
        assert guard.find_glob_symbols("src/**/*.ts") == []

    def test_lowercase_concept_has_no_symbols(self):
        assert guard.find_glob_symbols("*auth*") == []

    def test_short_token_has_no_symbols(self):
        assert guard.find_glob_symbols("*Foo*") == []

    def test_zero_width_stripped_before_detection(self):
        # A zero-width space inside the symbol must not hide it from detection.
        assert guard.find_glob_symbols("*User\u200bService*") == ["UserService"]


# ---------------------------------------------------------------------------
# Unit tests: resolve_providers
# ---------------------------------------------------------------------------


class TestResolveProviders:
    @patch("invoke_lsp_glob_guard.detect_providers", return_value=["serena"])
    def test_extension_case_uses_detect(self, mock_detect):
        assert guard.resolve_providers("*Foo*.ts", "/project") == ["serena"]
        mock_detect.assert_called_once()
        # The synthetic target carries the glob's extension.
        assert mock_detect.call_args[0][0].endswith(".ts")

    @patch("invoke_lsp_glob_guard.detect_providers", return_value=[])
    def test_non_code_extension_yields_empty(self, _mock_detect):
        assert guard.resolve_providers("*UserService*.md", "/project") == []

    @patch("invoke_lsp_glob_guard.detect_providers", return_value=["serena"])
    def test_bare_symbol_probes_programming_languages(self, _mock_detect):
        # First probed programming extension that returns a provider wins.
        assert guard.resolve_providers("*UserService*", "/project") == ["serena"]

    @patch("invoke_lsp_glob_guard.detect_providers", return_value=[])
    def test_bare_symbol_no_provider_returns_empty(self, _mock_detect):
        # Full probe loop runs (covers the non-programming continue and the
        # final empty return) when nothing is configured.
        assert guard.resolve_providers("*UserService*", "/project") == []


# ---------------------------------------------------------------------------
# Unit tests: build_guidance
# ---------------------------------------------------------------------------


class TestBuildGuidance:
    def test_names_pattern_symbols_and_count(self):
        text = guard.build_guidance("*UserService*", ["UserService"], ["serena"])
        assert "UserService" in text
        assert "1 code symbol(s)" in text
        assert "*UserService*" in text

    def test_pascal_uses_definition_tool(self):
        text = guard.build_guidance("*UserService*", ["UserService"], ["serena"])
        assert "find_symbol" in text

    def test_lowercase_uses_references_tool(self):
        text = guard.build_guidance("*createOrder*", ["createOrder"], ["serena"])
        assert "find_referencing_symbols" in text

    def test_includes_recovery_actions(self):
        text = guard.build_guidance("*UserService*", ["UserService"], ["serena"])
        assert "activate_project" in text
        assert "initial_instructions" in text
        assert "SKIP_LSP_GATE" in text

    def test_native_lsp_provider_renders(self):
        text = guard.build_guidance("*UserService*", ["UserService"], ["native_lsp"])
        assert "native LSP" in text

    def test_unknown_provider_key_skipped(self):
        text = guard.build_guidance("*UserService*", ["UserService"], ["bogus", "serena"])
        assert "find_symbol" in text

    def test_provider_without_tool_skipped(self, monkeypatch: pytest.MonkeyPatch):
        toolless = {"label": "empty", "prefix": "mcp__empty__", "tools": {}}
        monkeypatch.setitem(guard.PROVIDERS, "empty", toolless)
        text = guard.build_guidance("*UserService*", ["UserService"], ["empty", "serena"])
        assert "mcp__empty__" not in text
        assert "find_symbol" in text

    def test_no_dashes(self):
        text = guard.build_guidance("*UserService*", ["UserService"], ["serena", "native_lsp"])
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
        mock_stdin(json.dumps({"tool_name": "Read", "tool_input": {"file_path": "x"}}))
        assert guard.main() == 0

    def test_non_dict_tool_input_allows(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Glob", "tool_input": "string"}))
        assert guard.main() == 0

    def test_missing_tool_input_allows(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Glob"}))
        assert guard.main() == 0

    def test_empty_pattern_allows(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Glob", "tool_input": {"pattern": ""}}))
        assert guard.main() == 0

    def test_extension_only_pattern_allows(self, mock_stdin: Callable[[str], None]):
        mock_stdin(_glob_input("src/**/*.ts"))
        assert guard.main() == 0

    def test_lowercase_concept_allows(self, mock_stdin: Callable[[str], None]):
        mock_stdin(_glob_input("*auth*"))
        assert guard.main() == 0

    def test_skip_lsp_gate_allows(
        self, mock_stdin: Callable[[str], None], monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("SKIP_LSP_GATE", "true")
        mock_stdin(_glob_input("*UserService*"))
        assert guard.main() == 0

    @patch("invoke_lsp_glob_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_glob_guard.detect_providers", return_value=["serena"])
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
        mock_stdin(_glob_input("*UserService*"))
        assert guard.main() == 0
        warn_once.assert_called_once_with("lsp-glob-guard", "/project")
        assert capsys.readouterr().out == ""

    def test_consumer_repo_skips(
        self, mock_stdin: Callable[[str], None], monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(guard, "skip_if_consumer_repo", lambda _name: True)
        mock_stdin(_glob_input("*UserService*"))
        assert guard.main() == 0

    def test_exception_fails_open(self, monkeypatch: pytest.MonkeyPatch):
        boom = MagicMock(isatty=MagicMock(side_effect=RuntimeError("boom")))
        monkeypatch.setattr("sys.stdin", boom)
        assert guard.main() == 0

    @patch("invoke_lsp_glob_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_glob_guard.detect_providers", return_value=[])
    def test_non_code_extension_with_symbol_allows(
        self, _mock_detect, _mock_dir, mock_stdin: Callable[[str], None]
    ):
        # A markdown glob carrying a symbol token has no symbol_navigation
        # capability: allow.
        mock_stdin(_glob_input("*UserService*.md"))
        assert guard.main() == 0

    @patch("invoke_lsp_glob_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_glob_guard.detect_providers", return_value=[])
    def test_no_provider_available_allows(
        self, _mock_detect, _mock_dir, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(_glob_input("*UserService*"))
        assert guard.main() == 0


# ---------------------------------------------------------------------------
# main(): block path (positive)
# ---------------------------------------------------------------------------


class TestBlock:
    @patch("invoke_lsp_glob_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_glob_guard.detect_providers", return_value=["serena"])
    def test_blocks_pascal_glob_with_extension(
        self, _mock_detect, _mock_dir, mock_stdin: Callable[[str], None], capsys
    ):
        mock_stdin(_glob_input("*UserService*.py"))
        assert guard.main() == 2
        captured = capsys.readouterr()
        assert "LSP-FIRST" in captured.out
        assert "find_symbol" in captured.out
        assert "blocked Glob" in captured.err

    @patch("invoke_lsp_glob_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_glob_guard.detect_providers", return_value=["serena"])
    def test_blocks_bare_symbol_glob(
        self, _mock_detect, _mock_dir, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(_glob_input("*UserService*"))
        assert guard.main() == 2

    @patch("invoke_lsp_glob_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_glob_guard.detect_providers", return_value=["serena"])
    def test_blocks_snake_function_glob(
        self, _mock_detect, _mock_dir, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(_glob_input("*get_user_sessions*"))
        assert guard.main() == 2


# ---------------------------------------------------------------------------
# main(): warn mode (LSP_GATE_MODE=warn)
# ---------------------------------------------------------------------------


class TestWarnMode:
    @patch("invoke_lsp_glob_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_glob_guard.detect_providers", return_value=["serena"])
    def test_warn_mode_allows_with_advisory(
        self,
        _mock_detect,
        _mock_dir,
        mock_stdin: Callable[[str], None],
        monkeypatch: pytest.MonkeyPatch,
        capsys,
    ):
        monkeypatch.setenv("LSP_GATE_MODE", "warn")
        mock_stdin(_glob_input("*UserService*"))
        assert guard.main() == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert "LSP-FIRST" in payload["systemMessage"]
        assert "warn mode" in captured.err

    @patch("invoke_lsp_glob_guard.get_project_directory", return_value="/project")
    @patch("invoke_lsp_glob_guard.detect_providers", return_value=["serena"])
    def test_block_mode_default_blocks(
        self,
        _mock_detect,
        _mock_dir,
        mock_stdin: Callable[[str], None],
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("LSP_GATE_MODE", "block")
        mock_stdin(_glob_input("*UserService*"))
        assert guard.main() == 2


# ---------------------------------------------------------------------------
# Integration: real lib wiring against this repo's config
# ---------------------------------------------------------------------------


class TestRealLibWiring:
    def test_real_detect_providers_blocks_bare_symbol(self, mock_stdin: Callable[[str], None]):
        """Without mocking the lib, a bare symbol glob blocks in this repo.

        This repo configures python in .serena/project.yml and registers the
        serena MCP server, so the bare-symbol probe finds a provider and the
        guard blocks. Confirms the bootstrap import and wiring are correct.
        """
        mock_stdin(_glob_input("*SessionManager*"))
        assert guard.main() == 2


# ---------------------------------------------------------------------------
# Entry points: module-as-script and runpy
# ---------------------------------------------------------------------------


class TestModuleAsScript:
    def test_runs_as_subprocess_allows_non_glob(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, _HOOK_PATH],
            input=json.dumps({"tool_name": "Read", "tool_input": {"file_path": "x"}}),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_runs_as_subprocess_blocks_symbol(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, _HOOK_PATH],
            input=_glob_input("*SessionManager*"),
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
            io.StringIO(json.dumps({"tool_name": "Read", "tool_input": {}})),
        )
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(_HOOK_PATH, run_name="__main__")
        assert exc_info.value.code == 0
