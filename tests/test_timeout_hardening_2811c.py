"""Subprocess timeout hardening, residual sites (issue #2943, deferred #2811).

The staged-file scan in detect_test_coverage_gaps must pass a timeout kwarg and
degrade gracefully when the subprocess hangs. See issue #2943.

The companion cases for ``invoke_observation_sync._get_repo_root`` were removed
with that hook when ADR-096 retired every tool-call hook. Their subject no
longer exists; nothing else calls the helper they covered.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import scripts.detect_test_coverage_gaps as _cov


def _ok_result(stdout: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = 0
    result.stdout = stdout
    result.stderr = ""
    return result


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
