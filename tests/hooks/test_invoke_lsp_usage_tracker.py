#!/usr/bin/env python3
"""Tests for the invoke_lsp_usage_tracker PostToolUse hook (ADR-062).

Covers: LSP navigation tool detection (Serena standalone, plugin-wrapped,
native LSP), state recording via record_nav, LSP_GATE_MODE=warn systemMessage,
and EVERY fail-open path (tty, empty stdin, malformed JSON, missing field,
tool_input/non-dict input, non-LSP tool, SKIP_LSP_GATE, consumer repo,
exception). PostToolUse always exits 0.

Coverage targets every branch in invoke_lsp_usage_tracker, including the
subprocess (stdin-fed) and runpy entry-point execution paths.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HOOK_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PostToolUse")
if HOOK_DIR not in sys.path:
    sys.path.insert(0, HOOK_DIR)

import invoke_lsp_usage_tracker  # noqa: E402

HOOK_PATH = str(
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "hooks"
    / "PostToolUse"
    / "invoke_lsp_usage_tracker.py"
)


# ---------------------------------------------------------------------------
# Unit tests for is_lsp_navigation_tool
# ---------------------------------------------------------------------------


class TestIsLspNavigationTool:
    def test_serena_find_symbol(self):
        assert invoke_lsp_usage_tracker.is_lsp_navigation_tool(
            "mcp__serena__find_symbol"
        )

    def test_serena_find_referencing_symbols(self):
        assert invoke_lsp_usage_tracker.is_lsp_navigation_tool(
            "mcp__serena__find_referencing_symbols"
        )

    def test_serena_get_symbols_overview(self):
        assert invoke_lsp_usage_tracker.is_lsp_navigation_tool(
            "mcp__serena__get_symbols_overview"
        )

    def test_serena_find_implementations(self):
        assert invoke_lsp_usage_tracker.is_lsp_navigation_tool(
            "mcp__serena__find_implementations"
        )

    def test_serena_get_diagnostics_for_file(self):
        assert invoke_lsp_usage_tracker.is_lsp_navigation_tool(
            "mcp__serena__get_diagnostics_for_file"
        )

    def test_native_lsp_tool(self):
        assert invoke_lsp_usage_tracker.is_lsp_navigation_tool("LSP")

    def test_plugin_wrapped_serena(self):
        assert invoke_lsp_usage_tracker.is_lsp_navigation_tool(
            "mcp__plugin_serena__find_symbol"
        )

    def test_plugin_wrapped_serena_with_suffix(self):
        # Plugin segment containing 'serena' as a substring (token-anywhere).
        assert invoke_lsp_usage_tracker.is_lsp_navigation_tool(
            "mcp__plugin_myserenamcp__get_symbols_overview"
        )

    def test_serena_non_symbolic_tool_rejected(self):
        # write_memory is a serena tool but NOT navigation (stricter than kit).
        assert not invoke_lsp_usage_tracker.is_lsp_navigation_tool(
            "mcp__serena__write_memory"
        )

    def test_serena_onboarding_rejected(self):
        assert not invoke_lsp_usage_tracker.is_lsp_navigation_tool(
            "mcp__serena__onboarding"
        )

    def test_unknown_mcp_tool_rejected(self):
        assert not invoke_lsp_usage_tracker.is_lsp_navigation_tool(
            "mcp__foo__bar"
        )

    def test_plugin_wrapped_non_serena_rejected(self):
        assert not invoke_lsp_usage_tracker.is_lsp_navigation_tool(
            "mcp__plugin_context-mode_context-mode__ctx_search"
        )

    def test_empty_string_rejected(self):
        assert not invoke_lsp_usage_tracker.is_lsp_navigation_tool("")

    def test_non_string_rejected(self):
        assert not invoke_lsp_usage_tracker.is_lsp_navigation_tool(None)  # type: ignore[arg-type]

    def test_non_string_int_rejected(self):
        assert not invoke_lsp_usage_tracker.is_lsp_navigation_tool(42)  # type: ignore[arg-type]

    def test_plain_non_mcp_tool_rejected(self):
        assert not invoke_lsp_usage_tracker.is_lsp_navigation_tool("Bash")


# ---------------------------------------------------------------------------
# Unit tests for _gate_mode
# ---------------------------------------------------------------------------


class TestGateMode:
    def test_default_is_block(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("LSP_GATE_MODE", raising=False)
        assert invoke_lsp_usage_tracker._gate_mode() == "block"

    def test_warn_mode(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LSP_GATE_MODE", "warn")
        assert invoke_lsp_usage_tracker._gate_mode() == "warn"

    def test_warn_mode_with_whitespace(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LSP_GATE_MODE", "  warn  ")
        assert invoke_lsp_usage_tracker._gate_mode() == "warn"

    def test_unknown_mode_is_block(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LSP_GATE_MODE", "loud")
        assert invoke_lsp_usage_tracker._gate_mode() == "block"


# ---------------------------------------------------------------------------
# Unit tests for _emit_warn_message
# ---------------------------------------------------------------------------


class TestEmitWarnMessage:
    def test_emits_system_message_json(self, capsys):
        state = {"warmup_done": True, "nav_count": 3}
        invoke_lsp_usage_tracker._emit_warn_message("LSP", state)
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert "systemMessage" in payload
        assert "nav_count=3" in payload["systemMessage"]
        assert "advisory only" in payload["systemMessage"]

    def test_handles_missing_keys(self, capsys):
        # Defensive: state without keys must not raise.
        invoke_lsp_usage_tracker._emit_warn_message("LSP", {})
        payload = json.loads(capsys.readouterr().out)
        assert "nav_count=0" in payload["systemMessage"]


# ---------------------------------------------------------------------------
# main(): fail-open paths (all exit 0)
# ---------------------------------------------------------------------------


class TestMainFailOpen:
    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_skip_lsp_gate(
        self, _skip, monkeypatch: pytest.MonkeyPatch, mock_stdin
    ):
        monkeypatch.setenv("SKIP_LSP_GATE", "true")
        mock_stdin(json.dumps({"tool_name": "mcp__serena__find_symbol"}))
        with patch("invoke_lsp_usage_tracker.record_nav") as rec:
            assert invoke_lsp_usage_tracker.main() == 0
            rec.assert_not_called()

    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_tty(self, _skip, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        assert invoke_lsp_usage_tracker.main() == 0

    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_empty_stdin(
        self, _skip, monkeypatch: pytest.MonkeyPatch, mock_stdin
    ):
        monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
        mock_stdin("")
        assert invoke_lsp_usage_tracker.main() == 0

    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_malformed_json(
        self, _skip, monkeypatch: pytest.MonkeyPatch, mock_stdin
    ):
        monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
        mock_stdin("not json {")
        assert invoke_lsp_usage_tracker.main() == 0

    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_non_dict_input(
        self, _skip, monkeypatch: pytest.MonkeyPatch, mock_stdin
    ):
        monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
        mock_stdin(json.dumps(["a", "list"]))
        assert invoke_lsp_usage_tracker.main() == 0

    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_missing_tool_name(
        self, _skip, monkeypatch: pytest.MonkeyPatch, mock_stdin
    ):
        monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
        mock_stdin(json.dumps({"tool_input": {"file_path": "/x.py"}}))
        with patch("invoke_lsp_usage_tracker.record_nav") as rec:
            assert invoke_lsp_usage_tracker.main() == 0
            rec.assert_not_called()

    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_non_string_tool_name(
        self, _skip, monkeypatch: pytest.MonkeyPatch, mock_stdin
    ):
        monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
        mock_stdin(json.dumps({"tool_name": 123}))
        assert invoke_lsp_usage_tracker.main() == 0

    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_non_lsp_tool(
        self, _skip, monkeypatch: pytest.MonkeyPatch, mock_stdin
    ):
        monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
        mock_stdin(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}))
        with patch("invoke_lsp_usage_tracker.record_nav") as rec:
            assert invoke_lsp_usage_tracker.main() == 0
            rec.assert_not_called()

    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_serena_non_symbolic_tool(
        self, _skip, monkeypatch: pytest.MonkeyPatch, mock_stdin
    ):
        monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
        mock_stdin(json.dumps({"tool_name": "mcp__serena__write_memory"}))
        with patch("invoke_lsp_usage_tracker.record_nav") as rec:
            assert invoke_lsp_usage_tracker.main() == 0
            rec.assert_not_called()

    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=True)
    def test_exits_0_on_consumer_repo(self, _skip, mock_stdin):
        mock_stdin(json.dumps({"tool_name": "mcp__serena__find_symbol"}))
        with patch("invoke_lsp_usage_tracker.record_nav") as rec:
            assert invoke_lsp_usage_tracker.main() == 0
            rec.assert_not_called()

    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=False)
    def test_fails_open_on_exception(
        self, _skip, monkeypatch: pytest.MonkeyPatch, mock_stdin
    ):
        monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
        mock_stdin(json.dumps({"tool_name": "mcp__serena__find_symbol"}))
        with patch(
            "invoke_lsp_usage_tracker.record_nav",
            side_effect=RuntimeError("boom"),
        ):
            assert invoke_lsp_usage_tracker.main() == 0


# ---------------------------------------------------------------------------
# main(): positive recording (block mode default)
# ---------------------------------------------------------------------------


class TestMainRecords:
    @patch("invoke_lsp_usage_tracker.get_project_directory", return_value="/proj")
    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=False)
    def test_records_nav_for_serena_symbol(
        self,
        _skip,
        _dir,
        monkeypatch: pytest.MonkeyPatch,
        mock_stdin,
        capsys,
    ):
        monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
        monkeypatch.delenv("LSP_GATE_MODE", raising=False)
        mock_stdin(json.dumps({"tool_name": "mcp__serena__find_symbol"}))
        with patch(
            "invoke_lsp_usage_tracker.record_nav",
            return_value={"warmup_done": True, "nav_count": 1},
        ) as rec:
            assert invoke_lsp_usage_tracker.main() == 0
            rec.assert_called_once_with("/proj")
        err = capsys.readouterr().err
        assert "LSP usage tracked" in err
        assert "nav_count=1" in err

    @patch("invoke_lsp_usage_tracker.get_project_directory", return_value="/proj")
    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=False)
    def test_records_nav_for_native_lsp(
        self, _skip, _dir, monkeypatch: pytest.MonkeyPatch, mock_stdin
    ):
        monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
        monkeypatch.delenv("LSP_GATE_MODE", raising=False)
        mock_stdin(json.dumps({"tool_name": "LSP"}))
        with patch(
            "invoke_lsp_usage_tracker.record_nav",
            return_value={"warmup_done": True, "nav_count": 0},
        ) as rec:
            assert invoke_lsp_usage_tracker.main() == 0
            rec.assert_called_once_with("/proj")

    @patch("invoke_lsp_usage_tracker.get_project_directory", return_value="/proj")
    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=False)
    def test_records_nav_for_plugin_wrapped(
        self, _skip, _dir, monkeypatch: pytest.MonkeyPatch, mock_stdin
    ):
        monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
        monkeypatch.delenv("LSP_GATE_MODE", raising=False)
        mock_stdin(
            json.dumps({"tool_name": "mcp__plugin_serena__get_symbols_overview"})
        )
        with patch(
            "invoke_lsp_usage_tracker.record_nav",
            return_value={"warmup_done": True, "nav_count": 2},
        ) as rec:
            assert invoke_lsp_usage_tracker.main() == 0
            rec.assert_called_once_with("/proj")

    @patch("invoke_lsp_usage_tracker.get_project_directory", return_value="/proj")
    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=False)
    def test_warn_mode_emits_system_message(
        self,
        _skip,
        _dir,
        monkeypatch: pytest.MonkeyPatch,
        mock_stdin,
        capsys,
    ):
        monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
        monkeypatch.setenv("LSP_GATE_MODE", "warn")
        mock_stdin(json.dumps({"tool_name": "mcp__serena__find_symbol"}))
        with patch(
            "invoke_lsp_usage_tracker.record_nav",
            return_value={"warmup_done": True, "nav_count": 4},
        ):
            assert invoke_lsp_usage_tracker.main() == 0
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert "systemMessage" in payload
        assert "nav_count=4" in payload["systemMessage"]


# ---------------------------------------------------------------------------
# End-to-end: real state lib, real record (integration through record_nav)
# ---------------------------------------------------------------------------


class TestEndToEndState:
    @patch("invoke_lsp_usage_tracker.get_project_directory")
    @patch("invoke_lsp_usage_tracker.skip_if_consumer_repo", return_value=False)
    def test_first_call_warms_up_second_increments_nav(
        self,
        _skip,
        mock_dir,
        monkeypatch: pytest.MonkeyPatch,
        mock_stdin,
        tmp_path: Path,
    ):
        # Real state lib, isolated state dir via XDG_STATE_HOME.
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
        monkeypatch.delenv("LSP_GATE_MODE", raising=False)
        proj = str(tmp_path / "proj")
        mock_dir.return_value = proj

        from hook_utilities.lsp_gate_state import read_state, reset_state

        reset_state(proj)

        # First navigation call: warmup only, nav_count stays 0.
        mock_stdin(json.dumps({"tool_name": "mcp__serena__find_symbol"}))
        assert invoke_lsp_usage_tracker.main() == 0
        state = read_state(proj)
        assert state["warmup_done"] is True
        assert state["nav_count"] == 0

        # Second navigation call: nav_count increments.
        mock_stdin(json.dumps({"tool_name": "mcp__serena__find_referencing_symbols"}))
        assert invoke_lsp_usage_tracker.main() == 0
        state = read_state(proj)
        assert state["nav_count"] == 1

        reset_state(proj)


# ---------------------------------------------------------------------------
# Entry-point coverage: subprocess (stdin-fed) and runpy
# ---------------------------------------------------------------------------


class TestEntryPoint:
    def test_subprocess_empty_stdin_exits_0(self):
        result = subprocess.run(
            ["python3", HOOK_PATH],
            input="",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_subprocess_serena_tool_exits_0(self, tmp_path: Path):
        import os

        env = dict(os.environ)
        env["XDG_STATE_HOME"] = str(tmp_path)
        env.pop("SKIP_LSP_GATE", None)
        env.pop("LSP_GATE_MODE", None)
        result = subprocess.run(
            ["python3", HOOK_PATH],
            input=json.dumps({"tool_name": "mcp__serena__find_symbol"}),
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert "LSP usage tracked" in result.stderr

    def test_subprocess_non_lsp_tool_exits_0(self):
        result = subprocess.run(
            ["python3", HOOK_PATH],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_main_guard_via_runpy(self, monkeypatch: pytest.MonkeyPatch):
        """Cover the sys.exit(main()) line via runpy in-process execution."""
        import runpy

        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(HOOK_PATH, run_name="__main__")
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# Bootstrap failure path: lib dir not found -> exit 0 (fail-open)
# ---------------------------------------------------------------------------


class TestBootstrapFailOpen:
    def test_bootstrap_missing_lib_exits_0(self, tmp_path: Path):
        """If CLAUDE_PLUGIN_ROOT points nowhere useful, the hook exits 0."""
        import os

        env = dict(os.environ)
        # Point plugin root at an empty dir: lib/ will not exist -> bootstrap
        # prints and exits 0 (PostToolUse never blocks).
        env["CLAUDE_PLUGIN_ROOT"] = str(tmp_path)
        result = subprocess.run(
            ["python3", HOOK_PATH],
            input=json.dumps({"tool_name": "mcp__serena__find_symbol"}),
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert "Plugin lib directory not found" in result.stderr
