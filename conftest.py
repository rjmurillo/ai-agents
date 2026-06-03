"""Repository-wide pytest safety guards."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent


def _real_repo_head() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def pytest_configure(config: pytest.Config) -> None:
    config._real_repo_expected_head = _real_repo_head()  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _guard_real_repo_head(request: pytest.FixtureRequest):
    """Fail the test if it moved or corrupted the real repo HEAD (#2316)."""
    expected = getattr(request.config, "_real_repo_expected_head", None)
    yield
    after = _real_repo_head()
    if expected and expected != after:
        after_str = after[:8] if after else "None (corrupted/deleted)"
        pytest.fail(
            f"#2316: this test mutated the REAL repo HEAD "
            f"({expected[:8]} -> {after_str}). A git mutation ran in the repo "
            f"worktree instead of an isolated tmp repo. Isolate it: init a repo "
            f"in tmp_path and run every git command with cwd=<tmp repo>.",
            pytrace=False,
        )
