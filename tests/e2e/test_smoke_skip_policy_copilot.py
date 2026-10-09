"""Always-on tests for ``skip_or_fail_on_copilot_block`` (owner decision D26).

A quota block skips with the marker. Any other block fails in CI and skips
without the marker locally. No CLI, auth, or credits are needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.lib.smoke_block_samples import NON_QUOTA_STDERR, QUOTA_STDERR, completed

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
_original_sys_path = sys.path.copy()
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from smoke_skip_policy import QUOTA_SKIP_MARKER, skip_or_fail_on_copilot_block
finally:
    sys.path[:] = _original_sys_path


def test_skip_or_fail_on_copilot_block_ignores_an_unblocked_run() -> None:
    skip_or_fail_on_copilot_block(completed(returncode=0))


def test_quota_block_skips_with_the_marker_in_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(pytest.skip.Exception) as skipped:
        skip_or_fail_on_copilot_block(completed(stderr=QUOTA_STDERR, returncode=1))
    assert str(skipped.value).startswith(QUOTA_SKIP_MARKER)


@pytest.mark.parametrize("stderr", NON_QUOTA_STDERR.values(), ids=NON_QUOTA_STDERR.keys())
def test_non_quota_block_fails_in_ci(monkeypatch: pytest.MonkeyPatch, stderr: str) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(pytest.fail.Exception):
        skip_or_fail_on_copilot_block(completed(stderr=stderr, returncode=1))


@pytest.mark.parametrize("stderr", NON_QUOTA_STDERR.values(), ids=NON_QUOTA_STDERR.keys())
def test_non_quota_block_skips_loudly_without_the_marker_locally(
    monkeypatch: pytest.MonkeyPatch, stderr: str
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(pytest.skip.Exception) as skipped:
        skip_or_fail_on_copilot_block(completed(stderr=stderr, returncode=1))
    assert QUOTA_SKIP_MARKER not in str(skipped.value)
