"""Tests for the ai-review infrastructure-failure classifier.

The classifier lives in ``.github/actions/ai-review/action.yml`` as the
``is_infrastructure_failure`` Bash function. The same logic is mirrored in
``.github/actions/ai-review/test-infrastructure-failure.sh`` (a standalone
harness explicitly "extracted from action.yml for testability"). These tests
drive that harness so the classification contract is guarded by CI.

Regression focus (Renovate CI block): a retired/unknown model name makes the
Copilot CLI exit non-zero with a stderr like
``Error: Model "X" from --model flag is not available.`` and empty stdout. That
must classify as an infrastructure failure so the review degrades to a
non-blocking warning instead of hard-failing every required review check.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "actions"
    / "ai-review"
    / "test-infrastructure-failure.sh"
)

_MODEL_UNAVAILABLE_STDERR = (
    'Error: Model "claude-opus-4.5" from --model flag is not available.'
)


def _classify(exit_code: int, stdout: str, stderr: str) -> str:
    """Return the harness verdict ("true"/"false") for the given inputs."""
    result = subprocess.run(
        ["bash", str(_SCRIPT), str(exit_code), stdout, stderr],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_script_exists() -> None:
    """The extracted classifier harness is present."""
    assert _SCRIPT.is_file(), f"missing classifier harness: {_SCRIPT}"


@pytest.mark.parametrize(
    ("exit_code", "stdout", "stderr"),
    [
        # Retired/unknown model name (the Renovate CI block). Non-zero exit,
        # empty stdout, model error on stderr.
        (1, "", _MODEL_UNAVAILABLE_STDERR),
        # Timeout is exit code 124.
        (124, "", ""),
        # Non-zero exit with no output at all indicates infrastructure trouble.
        (1, "", ""),
        # Known infrastructure stderr keywords.
        (1, "", "Error: rate limit exceeded, retry later"),
        (1, "", "connection refused"),
        (1, "", "No authentication token provided"),
        (1, "", "HTTP 503 Service Unavailable"),
    ],
)
def test_infrastructure_failures_classified_true(
    exit_code: int, stdout: str, stderr: str
) -> None:
    """Infrastructure-style failures classify as infra (non-blocking)."""
    assert _classify(exit_code, stdout, stderr) == "true"


@pytest.mark.parametrize(
    ("exit_code", "stdout", "stderr"),
    [
        # Clean success.
        (0, "VERDICT: PASS", ""),
        # Genuine code-quality failure: a real verdict on stdout with no
        # infrastructure stderr must NOT be masked as infra, or blocking
        # findings would be silently downgraded.
        (1, "VERDICT: FAIL\nMESSAGE: real code issue", ""),
        (1, "VERDICT: CRITICAL_FAIL\nMESSAGE: blocking defect", ""),
    ],
)
def test_non_infrastructure_outcomes_classified_false(
    exit_code: int, stdout: str, stderr: str
) -> None:
    """Success and genuine code-quality failures are not infra failures."""
    assert _classify(exit_code, stdout, stderr) == "false"
