#!/usr/bin/env python3
"""Regression coverage for Issue #2757: the pre-push size gate bases its
merge-base on origin/main, not stale local ``main``.

In a linked worktree (or any checkout where local ``main`` lags origin/main),
``git merge-base main HEAD`` returns a stale base, so the commit-count /
PR-size gate over-counts both commits and files. The reported "23 commits /
146 files" against a true diff of "1 commit / 4 files" came from this bug.

Two layers of coverage:

1. Behavioral: a temp git repo where local ``main`` lags origin/main proves
   that the origin/main-based range gives the true count while the local-main
   range inflates it. This pins the git contract the hook depends on.
2. Content: the new-branch branch of the hook computes its merge-base against
   origin/main first and only falls back to local ``main``; it does a
   best-effort ``git fetch origin main`` so origin/main is fresh.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_PUSH = REPO_ROOT / ".githooks" / "pre-push"


def _pre_push_text() -> str:
    return PRE_PUSH.read_text(encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout.strip()


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    _git(repo, "config", "commit.gpgsign", "false")


def _commit(repo: Path, name: str, body: str = "x") -> None:
    (repo / name).write_text(body, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", f"add {name}")


@pytest.fixture()
def stale_local_main(tmp_path: Path) -> Path:
    """A clone whose local ``main`` lags origin/main, with a feature branch.

    Layout after setup:
      - origin advances local ``main`` by 3 extra commits, then the clone's
        local ``main`` ref is left pointing at the old base (the worktree /
        stale-checkout shape).
      - The feature branch adds exactly 1 commit and 1 file off the *fresh*
        origin/main tip.
    The true diff vs origin/main is 1 commit / 1 file; vs stale local ``main``
    it is 4 commits / 4 files (3 upstream + 1 feature).
    """
    origin = tmp_path / "origin"
    _init_repo(origin)
    _commit(origin, "base.txt")
    # Allow pushing into a non-bare repo's checked-out branch.
    _git(origin, "config", "receive.denyCurrentBranch", "ignore")

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    _git(clone, "config", "user.email", "dev@example.com")
    _git(clone, "config", "user.name", "Dev")
    _git(clone, "config", "commit.gpgsign", "false")

    # Record where local main currently sits (the stale base), then advance
    # origin/main by 3 commits without fast-forwarding the clone's local main.
    stale_main = _git(clone, "rev-parse", "main")
    for i in range(3):
        _commit(origin, f"upstream-{i}.txt")
    _git(clone, "fetch", "-q", "origin", "main")
    # Local ``main`` deliberately left at the stale base; origin/main is fresh.
    assert _git(clone, "rev-parse", "main") == stale_main
    assert _git(clone, "rev-parse", "origin/main") != stale_main

    # Feature branch off the FRESH origin/main: 1 commit / 1 file.
    _git(clone, "checkout", "-q", "-b", "feature", "origin/main")
    _commit(clone, "feature.txt")
    return clone


def test_origin_main_base_gives_true_count(stale_local_main: Path) -> None:
    # Arrange
    repo = stale_local_main
    head = _git(repo, "rev-parse", "HEAD")
    base = _git(repo, "merge-base", "origin/main", head)

    # Act
    count = _git(repo, "rev-list", "--count", f"{base}..{head}")
    files = _git(repo, "diff", "--name-only", f"{base}...{head}")

    # Assert: the true review delta is 1 commit / 1 file.
    assert count == "1"
    assert files.splitlines() == ["feature.txt"]


def test_stale_local_main_base_inflates_count(stale_local_main: Path) -> None:
    # Arrange: this is the pre-fix behavior the bug report describes.
    repo = stale_local_main
    head = _git(repo, "rev-parse", "HEAD")
    base = _git(repo, "merge-base", "main", head)

    # Act
    count = _git(repo, "rev-list", "--count", f"{base}..{head}")
    files = _git(repo, "diff", "--name-only", f"{base}...{head}")

    # Assert: stale local main pulls in the 3 upstream commits + feature = 4.
    assert count == "4"
    assert len(files.splitlines()) == 4


def test_new_branch_path_prefers_origin_main_merge_base() -> None:
    # Arrange
    text = _pre_push_text()
    start = text.index('if [ "$remote_sha" = "$ZERO" ]; then')
    end = text.index('\n    else\n', start)
    new_branch_block = text[start:end]

    # Assert: origin/main is the primary base; local main is only the fallback,
    # and origin/main appears before main in the block (fallback ordering).
    assert "git merge-base origin/main" in new_branch_block
    origin_idx = new_branch_block.index("git merge-base origin/main")
    local_idx = new_branch_block.index("git merge-base main")
    assert origin_idx < local_idx, "origin/main must be tried before local main"


def test_best_effort_fetch_origin_main_present() -> None:
    # Arrange
    text = _pre_push_text()

    # Assert: a non-fatal fetch refreshes origin/main before the ref loop.
    expected = (
        "env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \\\n"
        "    git fetch --no-tags --quiet origin main 2>/dev/null || true"
    )
    assert expected in text


def test_existing_branch_path_still_uses_origin_main() -> None:
    # Arrange: guard against regressing the already-correct existing-branch path.
    text = _pre_push_text()

    # Assert
    assert 'merge_base=$(git merge-base origin/main "$local_sha"' in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
