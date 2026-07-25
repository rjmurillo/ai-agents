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
        copilot_auth_failed,
        copilot_auth_rejected,
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


# Verbatim tail of the nightly-cli-smoke stderr on run 30148661127, where the
# secret was populated and the token had expired. It carries both the rejection
# and the CLI's generic "here is how to authenticate" list, so it is the exact
# shape that made a rejected token read as an empty one (issue #3275).
_REJECTED_STDERR = (
    "Failed to fetch PAT user login (401): GitHub returned: Bad credentials\n"
    "No authentication information found. You can use any of the following "
    "methods:\n  - Set the COPILOT_GITHUB_TOKEN environment variable\n"
)


def test_auth_rejected_detects_bad_credentials() -> None:
    """A populated but refused token is recognized as rejected, not absent."""
    result = _completed(stderr=_REJECTED_STDERR, returncode=1)
    assert copilot_auth_rejected(result) is True


def test_auth_rejected_matches_the_pat_lookup_failure_alone() -> None:
    """Either rejection marker suffices; neither depends on the other."""
    result = _completed(stderr="failed to fetch pat user login (401)", returncode=1)
    assert copilot_auth_rejected(result) is True


def test_auth_rejected_matches_stdout_and_is_case_insensitive() -> None:
    result = _completed(stdout="GitHub Returned: BAD CREDENTIALS", returncode=2)
    assert copilot_auth_rejected(result) is True


def test_auth_rejected_false_on_healthy_run() -> None:
    """rc=0 is never an auth failure, even if the text appears in model output."""
    result = _completed(stdout="explaining Bad credentials errors", returncode=0)
    assert copilot_auth_rejected(result) is False


def test_auth_rejected_false_when_only_absent_markers_present() -> None:
    """A genuinely empty secret must not be reported as a rejected one."""
    result = _completed(stderr="No authentication information found.", returncode=1)
    assert copilot_auth_rejected(result) is False


def test_auth_rejected_tolerates_none_streams() -> None:
    assert copilot_auth_rejected(_completed(stdout=None, stderr=None, returncode=1)) is False


def test_auth_failed_covers_both_classes_and_ignores_success() -> None:
    """The gate the smokes call fires for either auth failure and nothing else."""
    assert copilot_auth_failed(_completed(stderr=_REJECTED_STDERR, returncode=1)) is True
    assert (
        copilot_auth_failed(
            _completed(stderr="No authentication information found.", returncode=1)
        )
        is True
    )
    assert copilot_auth_failed(_completed(stderr="some other crash", returncode=1)) is False
    assert copilot_auth_failed(_completed(stderr=_REJECTED_STDERR, returncode=0)) is False


def test_headline_says_rotate_not_provision_for_a_rejected_token() -> None:
    """The regression: a rejected token used to be reported as an empty one.

    The remediation differs, so the headline has to differ. This is the exact
    stderr from run 30148661127, which matches the absent markers too.
    """
    headline = copilot_auth_absent_headline(_completed(stderr=_REJECTED_STDERR, returncode=1))
    assert "rejected" in headline
    assert "rotate" in headline
    assert "is empty" not in headline


def test_headline_still_says_provision_for_an_absent_token() -> None:
    headline = copilot_auth_absent_headline(
        _completed(stderr="No authentication information found.", returncode=1)
    )
    assert "is empty" in headline
    assert "provision" in headline.lower()
    assert "rejected" not in headline
