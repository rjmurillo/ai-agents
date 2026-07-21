#!/usr/bin/env python3
"""Always-on unit tests for the shared Copilot probe helpers (issue #3275).

The gated CLI smokes import ``copilot_hook_probe`` for the fired-hook probe and
the auth-absent detector. These unit tests exercise the pure detector without a
real CLI, so the fail-fast diagnostic is covered in ordinary PR CI (no
RUN_CLI_E2E, no auth, no credits).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
# Scope the mutation to the import so the added path never leaks into other
# tests in the session (gemini review, PR #3294).
_original_sys_path = sys.path.copy()
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from copilot_hook_probe import (  # noqa: E402
        copilot_auth_absent,
        copilot_auth_absent_headline,
    )
finally:
    sys.path[:] = _original_sys_path


def _completed(
    *, stdout: str | None = "", stderr: str | None = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["copilot"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_auth_absent_detects_missing_token_on_stderr() -> None:
    """The dead-secret signature on stderr is recognized (issue #3275)."""
    result = _completed(
        stderr="Error: No authentication information found. Set the COPILOT_GITHUB_TOKEN env var.",
        returncode=1,
    )
    assert copilot_auth_absent(result) is True


def test_auth_absent_detects_token_hint_alone() -> None:
    """The token-env hint alone is enough, even without the first-line phrase."""
    result = _completed(stderr="please Set the COPILOT_GITHUB_TOKEN variable", returncode=1)
    assert copilot_auth_absent(result) is True


def test_auth_absent_is_case_insensitive_and_matches_stdout() -> None:
    """A stream swap (auth line on stdout) and mixed case still match (#3275)."""
    result = _completed(stdout="NO AUTHENTICATION INFORMATION FOUND", stderr="", returncode=1)
    assert copilot_auth_absent(result) is True


def test_auth_absent_false_on_healthy_run() -> None:
    """A normal authenticated run is not misread as an auth failure."""
    result = _completed(stdout="ok", stderr="", returncode=0)
    assert copilot_auth_absent(result) is False


def test_auth_absent_false_when_marker_present_but_rc_zero() -> None:
    """A healthy run (rc=0) that echoes a marker string is not misclassified (#3275)."""
    result = _completed(stdout="No authentication information found", stderr="", returncode=0)
    assert copilot_auth_absent(result) is False


def test_auth_absent_tolerates_none_streams() -> None:
    """A timed-out or not-yet-run process (None streams) does not crash."""
    result = _completed(stdout=None, stderr=None, returncode=1)
    assert copilot_auth_absent(result) is False


def test_auth_absent_headline_leads_with_cause_and_tolerates_none() -> None:
    """The headline names the real cause, cites #3275, and survives None stderr."""
    headline = copilot_auth_absent_headline(_completed(stderr=None, returncode=1))
    assert headline.startswith("Copilot auth token is empty")
    assert "COPILOT_GITHUB_TOKEN" in headline
    assert "#3275" in headline


def test_auth_absent_headline_surfaces_rc_and_stdout() -> None:
    """A stdout-only auth failure stays actionable: rc and stdout appear (#3275)."""
    headline = copilot_auth_absent_headline(
        _completed(stdout="No authentication information found", stderr="", returncode=1)
    )
    assert "rc=1" in headline
    assert "No authentication information found" in headline
