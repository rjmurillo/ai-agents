"""Tests for the SessionStart invoke_lsp_session_reset hook (ADR-062 Section 4).

The hook is the trusted lifecycle reset signal for the conditional LSP-first
enforcement layer. It ALWAYS exits 0 (SessionStart hooks never block) and clears
the gate-state file for the current cwd via ``lsp_gate_state.reset_state``.

Coverage targets (100%, every path):
  - cwd resolution: JSON cwd field (string), missing cwd, non-string cwd,
    non-dict input, empty/whitespace stdin, tty stdin, malformed JSON.
  - kill switch: SKIP_LSP_GATE=true bypasses the reset, leaves state untouched.
  - mode: LSP_GATE_MODE=warn still runs the reset (advisory parity only).
  - reset outcome: success (file cleared, idempotent on missing), failure
    (reset_state returns False) both exit 0.
  - exception fail-open: any Exception inside main() exits 0.
  - entry points: subprocess feeding stdin JSON, and the
    ``if __name__ == '__main__': sys.exit(main())`` guard via runpy.

There is no exit-2 "block" path: a SessionStart hook can only allow. The
"positive vs negative" distinction here is reset-runs (state cleared) vs
reset-skipped (kill switch / state left intact). Both return 0.
"""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "SessionStart"
sys.path.insert(0, str(HOOK_DIR))

# Importable because the bootstrap added .claude/lib to sys.path on first import
# of any SessionStart hook; the shared lib also resolves via scripts.* package.
import invoke_lsp_session_reset  # noqa: E402

MOD = "invoke_lsp_session_reset"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure no inherited kill switch / mode env leaks between tests."""
    monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
    monkeypatch.delenv("LSP_GATE_MODE", raising=False)
    yield


# ---------------------------------------------------------------------------
# resolve_cwd: pure cwd selection logic
# ---------------------------------------------------------------------------


class TestResolveCwd:
    def test_uses_json_cwd_string(self):
        assert invoke_lsp_session_reset.resolve_cwd({"cwd": "/repo/here"}) == "/repo/here"

    def test_missing_cwd_falls_back_to_getcwd(self):
        with patch(f"{MOD}.os.getcwd", return_value="/fallback"):
            assert invoke_lsp_session_reset.resolve_cwd({}) == "/fallback"

    def test_non_string_cwd_falls_back(self):
        with patch(f"{MOD}.os.getcwd", return_value="/fallback"):
            assert invoke_lsp_session_reset.resolve_cwd({"cwd": 123}) == "/fallback"

    def test_empty_string_cwd_falls_back(self):
        with patch(f"{MOD}.os.getcwd", return_value="/fallback"):
            assert invoke_lsp_session_reset.resolve_cwd({"cwd": ""}) == "/fallback"

    def test_non_dict_input_falls_back(self):
        with patch(f"{MOD}.os.getcwd", return_value="/fallback"):
            assert invoke_lsp_session_reset.resolve_cwd(["not", "a", "dict"]) == "/fallback"
            assert invoke_lsp_session_reset.resolve_cwd(None) == "/fallback"


# ---------------------------------------------------------------------------
# main: kill switch
# ---------------------------------------------------------------------------


class TestKillSwitch:
    def test_skip_lsp_gate_bypasses_reset(
        self, monkeypatch: pytest.MonkeyPatch, capsys
    ):
        monkeypatch.setenv("SKIP_LSP_GATE", "true")
        with patch(f"{MOD}.reset_state") as mock_reset:
            assert invoke_lsp_session_reset.main() == 0
        mock_reset.assert_not_called()
        assert "SKIP_LSP_GATE=true" in capsys.readouterr().err

    def test_skip_lsp_gate_non_true_does_not_bypass(
        self, monkeypatch: pytest.MonkeyPatch, mock_stdin: Callable[[str], None]
    ):
        # Only the exact string "true" bypasses; anything else runs the reset.
        monkeypatch.setenv("SKIP_LSP_GATE", "1")
        mock_stdin("")
        with patch(f"{MOD}.reset_state", return_value=True) as mock_reset:
            assert invoke_lsp_session_reset.main() == 0
        mock_reset.assert_called_once()


# ---------------------------------------------------------------------------
# main: fail-open stdin handling
# ---------------------------------------------------------------------------


class TestStdinHandling:
    def test_tty_stdin_resets_process_cwd(self):
        with patch(f"{MOD}.sys.stdin", MagicMock(isatty=lambda: True)):
            with patch(f"{MOD}.os.getcwd", return_value="/proc/cwd"):
                with patch(f"{MOD}.reset_state", return_value=True) as mock_reset:
                    assert invoke_lsp_session_reset.main() == 0
        mock_reset.assert_called_once_with("/proc/cwd")

    def test_empty_stdin_resets_process_cwd(
        self, mock_stdin: Callable[[str], None]
    ):
        mock_stdin("")
        with patch(f"{MOD}.os.getcwd", return_value="/proc/cwd"):
            with patch(f"{MOD}.reset_state", return_value=True) as mock_reset:
                assert invoke_lsp_session_reset.main() == 0
        mock_reset.assert_called_once_with("/proc/cwd")

    def test_whitespace_stdin_resets_process_cwd(
        self, mock_stdin: Callable[[str], None]
    ):
        mock_stdin("   \n\t  ")
        with patch(f"{MOD}.os.getcwd", return_value="/proc/cwd"):
            with patch(f"{MOD}.reset_state", return_value=True) as mock_reset:
                assert invoke_lsp_session_reset.main() == 0
        mock_reset.assert_called_once_with("/proc/cwd")

    def test_malformed_json_resets_process_cwd(
        self, mock_stdin: Callable[[str], None]
    ):
        mock_stdin("{not valid json")
        with patch(f"{MOD}.os.getcwd", return_value="/proc/cwd"):
            with patch(f"{MOD}.reset_state", return_value=True) as mock_reset:
                assert invoke_lsp_session_reset.main() == 0
        mock_reset.assert_called_once_with("/proc/cwd")

    def test_valid_json_with_cwd_resets_that_cwd(
        self, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(json.dumps({"cwd": "/given/repo", "session_id": "abc"}))
        with patch(f"{MOD}.reset_state", return_value=True) as mock_reset:
            assert invoke_lsp_session_reset.main() == 0
        mock_reset.assert_called_once_with("/given/repo")

    def test_valid_json_missing_cwd_resets_process_cwd(
        self, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(json.dumps({"session_id": "abc"}))
        with patch(f"{MOD}.os.getcwd", return_value="/proc/cwd"):
            with patch(f"{MOD}.reset_state", return_value=True) as mock_reset:
                assert invoke_lsp_session_reset.main() == 0
        mock_reset.assert_called_once_with("/proc/cwd")

    def test_valid_json_non_dict_resets_process_cwd(
        self, mock_stdin: Callable[[str], None]
    ):
        # JSON parses but is a list, not a dict -> resolve_cwd falls back.
        mock_stdin(json.dumps(["unexpected", "shape"]))
        with patch(f"{MOD}.os.getcwd", return_value="/proc/cwd"):
            with patch(f"{MOD}.reset_state", return_value=True) as mock_reset:
                assert invoke_lsp_session_reset.main() == 0
        mock_reset.assert_called_once_with("/proc/cwd")


# ---------------------------------------------------------------------------
# main: reset outcomes and mode
# ---------------------------------------------------------------------------


class TestResetOutcomes:
    def test_reset_success_exits_0(self, mock_stdin: Callable[[str], None], capsys):
        mock_stdin(json.dumps({"cwd": "/repo"}))
        with patch(f"{MOD}.reset_state", return_value=True):
            assert invoke_lsp_session_reset.main() == 0
        assert "reset=True" in capsys.readouterr().err

    def test_reset_failure_still_exits_0(
        self, mock_stdin: Callable[[str], None], capsys
    ):
        # reset_state returning False (OSError swallowed in lib) must not block.
        mock_stdin(json.dumps({"cwd": "/repo"}))
        with patch(f"{MOD}.reset_state", return_value=False):
            assert invoke_lsp_session_reset.main() == 0
        assert "reset=False" in capsys.readouterr().err

    def test_warn_mode_still_runs_reset(
        self, monkeypatch: pytest.MonkeyPatch, mock_stdin: Callable[[str], None], capsys
    ):
        monkeypatch.setenv("LSP_GATE_MODE", "warn")
        mock_stdin(json.dumps({"cwd": "/repo"}))
        with patch(f"{MOD}.reset_state", return_value=True) as mock_reset:
            assert invoke_lsp_session_reset.main() == 0
        mock_reset.assert_called_once_with("/repo")
        assert "mode=warn" in capsys.readouterr().err

    def test_default_mode_is_block(
        self, mock_stdin: Callable[[str], None], capsys
    ):
        mock_stdin(json.dumps({"cwd": "/repo"}))
        with patch(f"{MOD}.reset_state", return_value=True):
            assert invoke_lsp_session_reset.main() == 0
        assert "mode=block" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main: exception fail-open
# ---------------------------------------------------------------------------


class TestExceptionFailOpen:
    def test_reset_state_raising_fails_open(
        self, mock_stdin: Callable[[str], None], capsys
    ):
        mock_stdin(json.dumps({"cwd": "/repo"}))
        with patch(f"{MOD}.reset_state", side_effect=RuntimeError("boom")):
            assert invoke_lsp_session_reset.main() == 0
        assert "lsp-session-reset error: RuntimeError" in capsys.readouterr().err

    def test_stdin_read_raising_fails_open(self, capsys):
        broken = MagicMock()
        broken.isatty.return_value = False
        broken.read.side_effect = OSError("pipe died")
        with patch(f"{MOD}.sys.stdin", broken):
            assert invoke_lsp_session_reset.main() == 0
        assert "lsp-session-reset error: OSError" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Integration: real reset against a real state file
# ---------------------------------------------------------------------------


class TestRealReset:
    def test_clears_existing_state_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, mock_stdin: Callable[[str], None]
    ):
        from hook_utilities import lsp_gate_state

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        cwd = "/some/project"
        # Seed a "surgical mode" state that a new session must not inherit.
        lsp_gate_state.write_state(
            cwd, {"warmup_done": True, "nav_count": 5, "read_count": 9}
        )
        assert lsp_gate_state.state_path(cwd).exists()

        mock_stdin(json.dumps({"cwd": cwd}))
        assert invoke_lsp_session_reset.main() == 0
        assert not lsp_gate_state.state_path(cwd).exists()

    def test_idempotent_when_no_state_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, mock_stdin: Callable[[str], None]
    ):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mock_stdin(json.dumps({"cwd": "/never/seen"}))
        # No file exists; reset is a no-op that still exits 0.
        assert invoke_lsp_session_reset.main() == 0


# ---------------------------------------------------------------------------
# Entry points: subprocess feeding stdin + runpy __main__ guard
# ---------------------------------------------------------------------------


class TestModuleAsScript:
    HOOK_PATH = str(HOOK_DIR / "invoke_lsp_session_reset.py")

    def _run(self, stdin_text: str, env: dict | None = None):
        run_env = dict(os.environ)
        if env:
            run_env.update(env)
        return subprocess.run(
            ["python3", self.HOOK_PATH],
            input=stdin_text,
            capture_output=True,
            text=True,
            env=run_env,
        )

    def test_subprocess_empty_stdin_exits_0(self):
        result = self._run("")
        assert result.returncode == 0

    def test_subprocess_valid_json_exits_0(self, tmp_path):
        result = self._run(
            json.dumps({"cwd": "/some/project"}),
            env={"XDG_STATE_HOME": str(tmp_path)},
        )
        assert result.returncode == 0

    def test_subprocess_malformed_json_exits_0(self):
        result = self._run("{garbage")
        assert result.returncode == 0

    def test_subprocess_kill_switch_exits_0(self):
        result = self._run(
            json.dumps({"cwd": "/some/project"}),
            env={"SKIP_LSP_GATE": "true"},
        )
        assert result.returncode == 0
        assert "SKIP_LSP_GATE=true" in result.stderr

    def test_main_guard_via_runpy(self):
        """Cover the ``sys.exit(main())`` line via in-process runpy execution."""
        with patch(f"{MOD}.sys.stdin", MagicMock(isatty=lambda: True)):
            with pytest.raises(SystemExit) as exc_info:
                runpy.run_path(self.HOOK_PATH, run_name="__main__")
        assert exc_info.value.code == 0
