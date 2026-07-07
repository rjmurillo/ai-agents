"""Subprocess timeout hardening, residual hook sites (issue #2943, deferred #2811).

Every git call on a hook path (SessionStart / PreToolUse / PostToolUse) and the
staged-file scan in detect_test_coverage_gaps must pass a timeout kwarg and
degrade gracefully when the subprocess hangs, so a wedged git call can never
hang the agent session. See issue #2943.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO = Path(__file__).resolve().parents[1]
_HOOKS = _REPO / ".claude" / "hooks"

# Match the import convention used by tests/hooks/* so every test shares one
# module object per hook (avoids sys.modules pollution across the session).
for _sub in ("PostToolUse", "PreToolUse", "SessionStart"):
    _p = str(_HOOKS / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import invoke_adr_review_guard as _adr  # noqa: E402
import invoke_observation_sync as _obs  # noqa: E402
import invoke_session_initialization_enforcer as _sess  # noqa: E402

import scripts.detect_test_coverage_gaps as _cov  # noqa: E402


def _ok_result(stdout: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = 0
    result.stdout = stdout
    result.stderr = ""
    return result


# --- observation_sync._get_repo_root --------------------------------------


def test_observation_sync_passes_timeout() -> None:
    with patch.object(_obs.subprocess, "run", return_value=_ok_result("/repo")) as run:
        _obs._get_repo_root()
    assert run.call_args.kwargs.get("timeout") == 5


def test_observation_sync_timeout_degrades_to_cwd() -> None:
    timeout = subprocess.TimeoutExpired(cmd="git", timeout=5)
    with patch.object(_obs.subprocess, "run", side_effect=timeout):
        result = _obs._get_repo_root()
    assert result == _obs.os.getcwd()


# --- adr_review_guard.get_staged_adr_changes ------------------------------


def test_adr_guard_passes_timeout() -> None:
    with patch.object(_adr.subprocess, "run", return_value=_ok_result("")) as run:
        _adr.get_staged_adr_changes()
    assert run.call_args.kwargs.get("timeout") == 5


def test_adr_guard_timeout_raises_runtime_error() -> None:
    timeout = subprocess.TimeoutExpired(cmd="git", timeout=5)
    with patch.object(_adr.subprocess, "run", side_effect=timeout):
        try:
            _adr.get_staged_adr_changes()
        except RuntimeError as exc:
            assert "timed out" in str(exc)
        else:
            raise AssertionError("expected RuntimeError on timeout")


# --- session_initialization_enforcer.get_current_branch -------------------


def test_session_enforcer_passes_timeout() -> None:
    with patch.object(_sess.subprocess, "run", return_value=_ok_result("main")) as run:
        _sess.get_current_branch()
    assert run.call_args.kwargs.get("timeout") == 5


def test_session_enforcer_timeout_returns_none() -> None:
    timeout = subprocess.TimeoutExpired(cmd="git", timeout=5)
    with patch.object(_sess.subprocess, "run", side_effect=timeout):
        assert _sess.get_current_branch() is None


# --- detect_test_coverage_gaps.get_staged_ps1_files -----------------------


def test_coverage_gaps_passes_timeout(tmp_path: Path) -> None:
    with patch.object(_cov.subprocess, "run", return_value=_ok_result("")) as run:
        _cov.get_staged_ps1_files(tmp_path)
    assert run.call_args.kwargs.get("timeout") == 10


def test_coverage_gaps_timeout_returns_empty(tmp_path: Path) -> None:
    timeout = subprocess.TimeoutExpired(cmd="git", timeout=10)
    with patch.object(_cov.subprocess, "run", side_effect=timeout):
        assert _cov.get_staged_ps1_files(tmp_path) == []
