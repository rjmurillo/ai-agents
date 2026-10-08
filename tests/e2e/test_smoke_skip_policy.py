"""Always-on unit tests for the smoke skip-or-fail policy (owner decision D26).

The marker covers budget exhaustion only. Auth, rate limit, transport, and
latency never carry it. No CLI, auth, or credits are needed. The Copilot and
Claude entry points live in the ``_copilot`` and ``_claude`` siblings.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.lib.smoke_block_samples import (
    NON_QUOTA_STDERR,
    QUOTA_AGENT_STDOUT,
    QUOTA_STDERR,
    completed,
)

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
_original_sys_path = sys.path.copy()
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from copilot_hook_probe import copilot_block_reason
    from smoke_skip_policy import (
        QUOTA_SKIP_MARKER,
        copilot_block_skip_reason,
        running_in_ci,
        skip_or_fail_on_latency,
    )
finally:
    sys.path[:] = _original_sys_path


@pytest.mark.parametrize(
    "result",
    [
        completed(stderr=QUOTA_STDERR, returncode=1),
        completed(stdout=QUOTA_AGENT_STDOUT, returncode=1),
    ],
    ids=["prose", "json_event"],
)
def test_copilot_402_quota_skip_reason_leads_with_the_marker(
    result: subprocess.CompletedProcess[str],
) -> None:
    assert copilot_block_skip_reason(result).startswith(QUOTA_SKIP_MARKER)


@pytest.mark.parametrize("stderr", NON_QUOTA_STDERR.values(), ids=NON_QUOTA_STDERR.keys())
def test_copilot_non_quota_block_skip_reason_has_no_marker(stderr: str) -> None:
    result = completed(stderr=stderr, returncode=1)
    assert copilot_block_reason(result) is not None
    assert QUOTA_SKIP_MARKER not in copilot_block_skip_reason(result)


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
