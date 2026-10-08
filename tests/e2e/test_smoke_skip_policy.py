"""Always-on unit tests for the smoke skip-or-fail policy (owner decision D26).

The marker covers budget exhaustion only. Auth, rate limit, transport, and
latency never carry it. No CLI, auth, or credits are needed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
_original_sys_path = sys.path.copy()
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from copilot_hook_probe import copilot_block_reason
    from smoke_skip_policy import (
        QUOTA_SKIP_MARKER,
        claude_block_reason,
        copilot_block_skip_reason,
        running_in_ci,
        skip_or_fail_on_claude_block,
        skip_or_fail_on_copilot_block,
        skip_or_fail_on_latency,
    )
finally:
    sys.path[:] = _original_sys_path


def _completed(
    *, stdout: str | None = "", stderr: str | None = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["copilot"], returncode=returncode, stdout=stdout, stderr=stderr
    )


_QUOTA_STDERR = (
    "\nYou have exceeded your monthly quota (Request ID: C612:60CD4:E4E4F:1063A0:6AA0928A)\n"
    "\n\nChanges    +0 -0\n"
    "AI Credits 0 (3s)\n"
    "Resume     copilot --resume=e3d31814-eee1-4944-9d77-c27710b7b0b7\n"
)
# The agent path emits JSON events instead of prose.
_QUOTA_AGENT_STDOUT = (
    '{"type":"error","data":{"statusCode":402,'
    '"providerCallId":"A52E:26C4B7:FF31F:12203A:6AA092B1",'
    '"errorCode":"quota_exceeded"},"id":"1726daed"}\n'
    '{"type":"result","exitCode":1}\n'
)

_AUTH_ABSENT_STDERR = "No authentication information found.\nSet COPILOT_GITHUB_TOKEN"
_AUTH_REJECTED_STDERR = "GitHub returned: Bad credentials"
_RATE_LIMIT_STDERR = "API rate limit exceeded for user ID 12345."
_TRANSPORT_STDERR = "Failed to fetch PAT user login: connection reset by peer."


def test_copilot_402_quota_skip_reason_leads_with_the_marker() -> None:
    result = _completed(stderr=_QUOTA_STDERR, returncode=1)
    assert copilot_block_skip_reason(result).startswith(QUOTA_SKIP_MARKER)


def test_copilot_402_json_event_skip_reason_leads_with_the_marker() -> None:
    result = _completed(stdout=_QUOTA_AGENT_STDOUT, returncode=1)
    assert copilot_block_skip_reason(result).startswith(QUOTA_SKIP_MARKER)


@pytest.mark.parametrize(
    "stderr",
    [_AUTH_ABSENT_STDERR, _AUTH_REJECTED_STDERR, _RATE_LIMIT_STDERR, _TRANSPORT_STDERR],
    ids=["auth_absent", "auth_rejected", "rate_limit", "transport"],
)
def test_copilot_non_quota_block_skip_reason_has_no_marker(stderr: str) -> None:
    result = _completed(stderr=stderr, returncode=1)
    assert copilot_block_reason(result) is not None
    assert QUOTA_SKIP_MARKER not in copilot_block_skip_reason(result)


def test_skip_or_fail_on_copilot_block_ignores_an_unblocked_run() -> None:
    skip_or_fail_on_copilot_block(_completed(returncode=0))


def test_quota_block_skips_with_the_marker_in_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(pytest.skip.Exception) as skipped:
        skip_or_fail_on_copilot_block(_completed(stderr=_QUOTA_STDERR, returncode=1))
    assert str(skipped.value).startswith(QUOTA_SKIP_MARKER)


@pytest.mark.parametrize(
    "stderr",
    [_AUTH_ABSENT_STDERR, _AUTH_REJECTED_STDERR, _RATE_LIMIT_STDERR, _TRANSPORT_STDERR],
    ids=["auth_absent", "auth_rejected", "rate_limit", "transport"],
)
def test_non_quota_block_fails_in_ci(monkeypatch: pytest.MonkeyPatch, stderr: str) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(pytest.fail.Exception):
        skip_or_fail_on_copilot_block(_completed(stderr=stderr, returncode=1))


@pytest.mark.parametrize(
    "stderr",
    [_AUTH_ABSENT_STDERR, _AUTH_REJECTED_STDERR, _RATE_LIMIT_STDERR, _TRANSPORT_STDERR],
    ids=["auth_absent", "auth_rejected", "rate_limit", "transport"],
)
def test_non_quota_block_skips_loudly_without_the_marker_locally(
    monkeypatch: pytest.MonkeyPatch, stderr: str
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(pytest.skip.Exception) as skipped:
        skip_or_fail_on_copilot_block(_completed(stderr=stderr, returncode=1))
    assert QUOTA_SKIP_MARKER not in str(skipped.value)


@pytest.mark.parametrize(
    ("env", "expected"),
    [({"GITHUB_ACTIONS": "true"}, True), ({"CI": "true"}, True), ({"CI": ""}, False), ({}, False)],
)
def test_running_in_ci_reads_ci_and_github_actions(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], expected: bool
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert running_in_ci() is expected


def test_latency_skip_fails_in_ci_and_skips_unmarked_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(pytest.fail.Exception):
        skip_or_fail_on_latency("copilot run exceeded 240s")
    monkeypatch.delenv("GITHUB_ACTIONS")
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(pytest.skip.Exception) as skipped:
        skip_or_fail_on_latency("copilot run exceeded 240s")
    assert QUOTA_SKIP_MARKER not in str(skipped.value)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Credit balance is too low", "quota"),
        ('{"api_error_status": 429, "result": "monthly spend limit"}', "quota"),
        ("weekly limit resets Monday", "quota"),
        ("OAuth session expired and could not be refreshed", "auth"),
        ("Failed to authenticate: token invalid", "auth"),
        ("some unknown error", None),
    ],
)
def test_claude_block_reason_separates_quota_from_auth(text: str, expected: str | None) -> None:
    run = subprocess.CompletedProcess(["claude"], 1, stdout=text, stderr="")
    assert claude_block_reason(run) == expected


def test_claude_block_reason_ignores_a_healthy_run() -> None:
    run = subprocess.CompletedProcess(["claude"], 0, stdout="Credit balance is too low", stderr="")
    assert claude_block_reason(run) is None


def test_claude_credit_balance_skips_with_the_marker() -> None:
    run = subprocess.CompletedProcess(["claude"], 1, stdout="Credit balance is too low", stderr="")
    with pytest.raises(pytest.skip.Exception) as skipped:
        skip_or_fail_on_claude_block(run, "claude run")
    assert str(skipped.value).startswith(QUOTA_SKIP_MARKER)


def test_claude_auth_block_fails_in_ci_and_skips_unmarked_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = subprocess.CompletedProcess(["claude"], 1, stdout="oauth session expired", stderr="")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(pytest.fail.Exception):
        skip_or_fail_on_claude_block(run, "claude run")
    monkeypatch.delenv("GITHUB_ACTIONS")
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(pytest.skip.Exception) as skipped:
        skip_or_fail_on_claude_block(run, "claude run")
    assert QUOTA_SKIP_MARKER not in str(skipped.value)


def test_claude_unclassified_failure_does_not_skip() -> None:
    run = subprocess.CompletedProcess(["claude"], 1, stdout="boom", stderr="")
    skip_or_fail_on_claude_block(run, "claude run")
