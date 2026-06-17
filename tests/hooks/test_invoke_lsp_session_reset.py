"""Tests for the SessionStart invoke_lsp_session_reset hook (ADR-062 Section 4).

The hook is the trusted lifecycle reset signal for the conditional LSP-first
enforcement layer. It ALWAYS exits 0 (SessionStart hooks never block) and clears
the gate-state file for the project directory via ``lsp_gate_state.reset_state``.

The hook uses ``get_project_directory()`` (matching the usage tracker and read
guard) to ensure all gates use the same state key, avoiding the bug where
session reset clears a different state file than the one guards read/write.

Coverage targets (100%, every path):
  - project directory: uses get_project_directory() which honors CLAUDE_PROJECT_DIR
    or git root, matching the usage tracker and read guard.
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
from unittest.mock import patch

import pytest

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
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    yield


# ---------------------------------------------------------------------------
# main: kill switch
# ---------------------------------------------------------------------------


class TestKillSwitch:
    def test_skip_lsp_gate_bypasses_reset(self, monkeypatch: pytest.MonkeyPatch, capsys):
        monkeypatch.setenv("SKIP_LSP_GATE", "true")
        with patch(f"{MOD}.reset_state") as mock_reset:
            assert invoke_lsp_session_reset.main() == 0
        mock_reset.assert_not_called()
        assert "SKIP_LSP_GATE=true" in capsys.readouterr().err

    def test_skip_lsp_gate_non_true_does_not_bypass(self, monkeypatch: pytest.MonkeyPatch):
        # Only the exact string "true" bypasses; anything else runs the reset.
        monkeypatch.setenv("SKIP_LSP_GATE", "1")
        with patch(f"{MOD}.get_project_directory", return_value="/workspace"):
            with patch(f"{MOD}.reset_state", return_value=True) as mock_reset:
                assert invoke_lsp_session_reset.main() == 0
        mock_reset.assert_called_once()


# ---------------------------------------------------------------------------
# main: project directory resolution (uses get_project_directory, not stdin)
# ---------------------------------------------------------------------------


class TestProjectDirectory:
    def test_uses_get_project_directory(self, capsys):
        """The hook uses get_project_directory() to match usage tracker and read guard."""
        with patch(f"{MOD}.get_project_directory", return_value="/my/project"):
            with patch(f"{MOD}.reset_state", return_value=True) as mock_reset:
                assert invoke_lsp_session_reset.main() == 0
        mock_reset.assert_called_once_with("/my/project")

    def test_honors_claude_project_dir_env(self, monkeypatch: pytest.MonkeyPatch):
        """CLAUDE_PROJECT_DIR is honored via get_project_directory()."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/env/specified/project")
        with patch(f"{MOD}.reset_state", return_value=True) as mock_reset:
            assert invoke_lsp_session_reset.main() == 0
        mock_reset.assert_called_once_with("/env/specified/project")


# ---------------------------------------------------------------------------
# main: reset outcomes and mode
# ---------------------------------------------------------------------------


class TestResetOutcomes:
    def test_reset_success_exits_0(self, capsys):
        with patch(f"{MOD}.get_project_directory", return_value="/repo"):
            with patch(f"{MOD}.reset_state", return_value=True):
                assert invoke_lsp_session_reset.main() == 0
        assert "reset=True" in capsys.readouterr().err

    def test_reset_failure_still_exits_0(self, capsys):
        # reset_state returning False (OSError swallowed in lib) must not block.
        with patch(f"{MOD}.get_project_directory", return_value="/repo"):
            with patch(f"{MOD}.reset_state", return_value=False):
                assert invoke_lsp_session_reset.main() == 0
        assert "reset=False" in capsys.readouterr().err

    def test_warn_mode_still_runs_reset(self, monkeypatch: pytest.MonkeyPatch, capsys):
        # warn mode affects read/grep/glob guards, not the reset itself.
        monkeypatch.setenv("LSP_GATE_MODE", "warn")
        with patch(f"{MOD}.get_project_directory", return_value="/repo"):
            with patch(f"{MOD}.reset_state", return_value=True) as mock_reset:
                assert invoke_lsp_session_reset.main() == 0
        mock_reset.assert_called_once_with("/repo")
        assert "mode=warn" in capsys.readouterr().err

    def test_default_mode_is_block(self, capsys):
        with patch(f"{MOD}.get_project_directory", return_value="/repo"):
            with patch(f"{MOD}.reset_state", return_value=True):
                assert invoke_lsp_session_reset.main() == 0
        assert "mode=block" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main: exception fail-open
# ---------------------------------------------------------------------------


class TestExceptionFailOpen:
    def test_reset_state_raising_fails_open(self, capsys):
        with patch(f"{MOD}.get_project_directory", return_value="/repo"):
            with patch(f"{MOD}.reset_state", side_effect=RuntimeError("boom")):
                assert invoke_lsp_session_reset.main() == 0
        err = capsys.readouterr().err
        assert "lsp-session-reset state error: RuntimeError" in err
        assert "marker_cleared=" in err

    def test_marker_clear_runs_when_reset_state_raises(self):
        with patch(f"{MOD}.get_project_directory", return_value="/repo"):
            with patch(f"{MOD}.reset_state", side_effect=RuntimeError("boom")):
                with patch(f"{MOD}.clear_lsp_down_marker", return_value=True) as mock_clear:
                    assert invoke_lsp_session_reset.main() == 0
        mock_clear.assert_called_once_with("/repo")

    def test_get_project_directory_raising_fails_open(self, capsys):
        with patch(f"{MOD}.get_project_directory", side_effect=OSError("git failed")):
            assert invoke_lsp_session_reset.main() == 0
        assert "lsp-session-reset error: OSError" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Integration: real reset against a real state file
# ---------------------------------------------------------------------------


class TestRealReset:
    def test_clears_existing_state_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        from hook_utilities import lsp_gate_state

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        project_dir = "/some/project"
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", project_dir)
        # Seed a "surgical mode" state that a new session must not inherit.
        lsp_gate_state.write_state(
            project_dir, {"warmup_done": True, "nav_count": 5, "read_count": 9}
        )
        assert lsp_gate_state.state_path(project_dir).exists()

        assert invoke_lsp_session_reset.main() == 0
        assert not lsp_gate_state.state_path(project_dir).exists()

    def test_idempotent_when_no_state_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/never/seen")
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

    def test_subprocess_empty_stdin_exits_0(self, tmp_path):
        result = self._run(
            "",
            env={"CLAUDE_PROJECT_DIR": "/some/project", "XDG_STATE_HOME": str(tmp_path)},
        )
        assert result.returncode == 0

    def test_subprocess_valid_json_exits_0(self, tmp_path):
        # stdin JSON is now ignored; the hook uses get_project_directory()
        result = self._run(
            json.dumps({"cwd": "/some/project"}),
            env={"CLAUDE_PROJECT_DIR": "/actual/project", "XDG_STATE_HOME": str(tmp_path)},
        )
        assert result.returncode == 0

    def test_subprocess_malformed_json_exits_0(self, tmp_path):
        # Malformed JSON doesn't matter since stdin is not read for cwd
        result = self._run(
            "{garbage",
            env={"CLAUDE_PROJECT_DIR": "/some/project", "XDG_STATE_HOME": str(tmp_path)},
        )
        assert result.returncode == 0

    def test_subprocess_kill_switch_exits_0(self):
        result = self._run(
            json.dumps({"cwd": "/some/project"}),
            env={"SKIP_LSP_GATE": "true"},
        )
        assert result.returncode == 0
        assert "SKIP_LSP_GATE=true" in result.stderr

    def test_main_guard_via_runpy(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        """Cover the ``sys.exit(main())`` line via in-process runpy execution."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/some/project")
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(self.HOOK_PATH, run_name="__main__")
        assert exc_info.value.code == 0
