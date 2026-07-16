"""Repository-wide pytest safety guards."""

from __future__ import annotations

import os
import subprocess
import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent
_GIT_ENV_OVERRIDES = {"GIT_COMMON_DIR", "GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"}


def _git_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key not in _GIT_ENV_OVERRIDES
    }


def _real_repo_head() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            env=_git_env(),
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _real_repo_head_subject() -> str:
    """Return the current HEAD commit subject, evidence for a concurrent commit."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            env=_git_env(),
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "<unknown>"
    return out.stdout.strip() if out.returncode == 0 else "<unknown>"


def _check_head_change(before: str | None, after: str | None) -> None:
    """Report (never fail) when the real repo HEAD moved during a test window.

    A test-caused git mutation and a concurrent external commit in the same
    worktree are indistinguishable from HEAD alone (#3109), so a mismatch is
    surfaced as a warning with the offending SHAs and the new commit subject,
    not an accusation against the current test (#2316). A human attributes the
    move from the evidence. ``before is None`` means the pre-test read failed,
    so there is nothing to compare and the guard stays silent.
    """
    if before is None or before == after:
        return
    after_str = after[:8] if after else "None (unreadable during concurrent git)"
    subject = _real_repo_head_subject()
    warnings.warn(
        f"#3109: real repo HEAD changed during this test's window "
        f"({before[:8]} -> {after_str}; new HEAD subject: {subject!r}). "
        f"This is most likely a concurrent external commit in this worktree, "
        f"not this test. If this test ran a git command against the repo root "
        f"instead of an isolated tmp repo, that is the bug: init a repo in "
        f"tmp_path and run every git command with cwd=<tmp repo>.",
        stacklevel=2,
    )


@pytest.fixture(autouse=True)
def _guard_real_repo_head() -> Iterator[None]:
    """Warn (not blame) when the real repo HEAD moves during a test (#2316, #3109).

    The baseline is captured at fixture entry, per test, so one concurrent
    external commit warns once on the in-flight test instead of failing every
    later test against a stale session-start SHA.
    """
    before = _real_repo_head()
    yield
    _check_head_change(before, _real_repo_head())
