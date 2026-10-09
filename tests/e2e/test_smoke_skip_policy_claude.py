"""Always-on tests for the Claude block classification and skip policy (D26).

Credit and spend-limit text is quota; session and token text is auth. No CLI,
auth, or credits are needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.lib.smoke_block_samples import claude_run

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
_original_sys_path = sys.path.copy()
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from smoke_skip_policy import (
        QUOTA_SKIP_MARKER,
        claude_block_reason,
        skip_or_fail_on_claude_block,
    )
finally:
    sys.path[:] = _original_sys_path


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
    assert claude_block_reason(claude_run(text)) == expected


def test_claude_block_reason_ignores_a_healthy_run() -> None:
    assert claude_block_reason(claude_run("Credit balance is too low", returncode=0)) is None


def test_claude_credit_balance_skips_with_the_marker() -> None:
    with pytest.raises(pytest.skip.Exception) as skipped:
        skip_or_fail_on_claude_block(claude_run("Credit balance is too low"), "claude run")
    assert str(skipped.value).startswith(QUOTA_SKIP_MARKER)


def test_claude_quota_skip_text_says_the_cli_cannot_tell_a_rate_limit_apart() -> None:
    with pytest.raises(pytest.skip.Exception) as skipped:
        skip_or_fail_on_claude_block(claude_run('{"api_error_status": 429}'), "claude run")
    text = str(skipped.value)
    assert text.startswith(QUOTA_SKIP_MARKER)
    assert "rate limit (429)" in text
    assert "does not distinguish quota, credit, and rate limit" in text


def test_claude_auth_block_fails_in_ci_and_skips_unmarked_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = claude_run("oauth session expired")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(pytest.fail.Exception):
        skip_or_fail_on_claude_block(run, "claude run")
    monkeypatch.delenv("GITHUB_ACTIONS")
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(pytest.skip.Exception) as skipped:
        skip_or_fail_on_claude_block(run, "claude run")
    assert QUOTA_SKIP_MARKER not in str(skipped.value)


def test_claude_unclassified_failure_does_not_skip() -> None:
    skip_or_fail_on_claude_block(claude_run("boom"), "claude run")
