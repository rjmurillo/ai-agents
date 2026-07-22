"""Subprocess timeout hardening, residual sites (issue #2943, deferred #2811).

Every remaining git call in the observation hook and the staged-file scan in
detect_test_coverage_gaps must pass a timeout kwarg and degrade gracefully when
the subprocess hangs. See issue #2943.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO = Path(__file__).resolve().parents[1]
_HOOKS = _REPO / ".claude" / "hooks"

# Match the import convention used by tests/hooks/* so every test shares one
# module object per hook (avoids sys.modules pollution across the session).
_post_tool_use = str(_HOOKS / "PostToolUse")
if _post_tool_use not in sys.path:
    sys.path.insert(0, _post_tool_use)

import invoke_observation_sync as _obs  # noqa: E402

import scripts.detect_test_coverage_gaps as _cov  # noqa: E402


def _ok_result(stdout: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = 0
    result.stdout = stdout
    result.stderr = ""
    return result


# --- observation_sync._get_repo_root --------------------------------------


def test_observation_sync_passes_timeout() -> None:
    with (
        patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": ""}),
        patch.object(_obs.subprocess, "run", return_value=_ok_result("/repo")) as run,
    ):
        _obs._get_repo_root()
    assert run.call_args.kwargs.get("timeout") == 5


def test_observation_sync_timeout_refuses_unverified_cwd() -> None:
    timeout = subprocess.TimeoutExpired(cmd="git", timeout=5)
    with (
        patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": ""}),
        patch.object(_obs.subprocess, "run", side_effect=timeout),
    ):
        result = _obs._get_repo_root()
    assert result is None


def test_observation_sync_missing_git_refuses_unverified_cwd() -> None:
    # git binary absent: subprocess.run raises FileNotFoundError (an OSError).
    # The helper must refuse an unverified cwd without surfacing the OSError.
    with (
        patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": ""}),
        patch.object(
            _obs.subprocess, "run", side_effect=FileNotFoundError("git")
        ),
    ):
        result = _obs._get_repo_root()
    assert result is None


# --- detect_test_coverage_gaps.get_staged_ps1_files -----------------------


def test_coverage_gaps_passes_timeout(tmp_path: Path) -> None:
    with patch.object(_cov.subprocess, "run", return_value=_ok_result("")) as run:
        _cov.get_staged_ps1_files(tmp_path)
    assert run.call_args.kwargs.get("timeout") == 10


def test_coverage_gaps_timeout_returns_empty(tmp_path: Path) -> None:
    timeout = subprocess.TimeoutExpired(cmd="git", timeout=10)
    with patch.object(_cov.subprocess, "run", side_effect=timeout):
        assert _cov.get_staged_ps1_files(tmp_path) == []


def test_coverage_gaps_missing_git_returns_empty(tmp_path: Path) -> None:
    # A missing or non-executable git raises FileNotFoundError (an OSError
    # subclass); it must degrade to "no files", not crash the scanner.
    with patch.object(_cov.subprocess, "run", side_effect=FileNotFoundError("git")):
        assert _cov.get_staged_ps1_files(tmp_path) == []
