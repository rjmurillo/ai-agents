"""Runtime guards for the shallow-graft class of CI defect (issue #4572).

A `git fetch --depth=1` writes `.git/shallow`, which git shares across the
whole repository and every worktree, and it severs ancestry traversal for
every later step in the same job. A plain `git fetch` afterwards does not
repair it.

Measured on a complete clone of this repository, before and after a single
`git fetch --depth=1 origin main`, with no other change:

    git rev-list base..head           0 commits  ->  2263 commits
    git diff --name-only base..head   0 paths    ->  290 paths
    git merge-tree --write-tree       rc 0       ->  rc 128
    git merge-base base head          rc 0       ->  rc 1

`git fetch --unshallow` removes the graft, and so does a `--deepen` large
enough to reach the root commit; both were measured against this repository.
The distinction matters because the remedy printed by
`_check_history_integrity` names `--unshallow`, and a reader who believed a
plain fetch sufficed is exactly how the defect shipped.

This module is the containment half: the CI entrypoints that resolve a range
must refuse to answer under a graft rather than answering wrongly. The
prevention half, the static invariant that no workflow writes the graft, lives
in test_shallow_fetch_workflow_invariant.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY = REPO_ROOT / "scripts" / "validation" / "git_hook_policy.py"


def _git(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")


@pytest.fixture
def graftable_clone(tmp_path: Path) -> tuple[Path, Path]:
    """An origin with two commits on main and a full clone of it.

    The clone starts complete, so a test can graft it with one fetch and
    compare against its own ungrafted control rather than against an assumption.
    """
    origin = tmp_path / "origin"
    _init(origin)
    (origin / "seed.py").write_text("x = 1\n", encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-qm", "seed")
    (origin / "later.py").write_text("y = 2\n", encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-qm", "later")

    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
    _git(clone, "config", "user.email", "t@example.com")
    _git(clone, "config", "user.name", "t")
    return origin, clone


def _run_policy(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """Drive the real CLI entrypoint against ``repo`` and return the result.

    `--repo-root` defaults to the directory the script itself lives in, which in
    CI is the checkout under test but in a test is this repository. Passing it
    explicitly is what points the gate at the scratch clone; without it every
    assertion below would measure ai-agents and pass for the wrong reason.

    Testing rule 8: the workflow step runs this program under `set -e`, so the
    contract under test is the process exit status, not a helper's return value.
    """
    return subprocess.run(
        [sys.executable, str(POLICY), "--repo-root", str(repo), *argv],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_suppression_diff_answers_on_a_complete_clone(
    graftable_clone: tuple[Path, Path],
) -> None:
    """Negative control for the graft test below.

    Without this the graft assertion cannot distinguish "the guard fired" from
    "this command fails in a scratch repository for some unrelated reason".
    """
    _, clone = graftable_clone
    result = _run_policy(clone, "security-suppressions-diff", "--base-ref", "origin/main")
    assert result.returncode == 0, result.stderr


def test_suppression_diff_refuses_to_measure_a_grafted_clone(
    graftable_clone: tuple[Path, Path],
) -> None:
    """Issue #4572: a shallow clone must fail closed, not measure a wider range.

    The discriminating input is a clone that is complete and then grafted by a
    single depth-limited fetch, with nothing else changed. Restoring the defect,
    by removing the `_check_history_integrity` call from
    `check_suppression_diff`, turns this exit 2 back into an exit 0 computed
    over the wrong range.
    """
    origin, clone = graftable_clone
    assert _git(clone, "rev-parse", "--is-shallow-repository").stdout.strip() == "false"

    fetch = _git(clone, "fetch", "--depth=1", str(origin), "main")
    assert fetch.returncode == 0, fetch.stderr
    assert _git(clone, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"

    result = _run_policy(clone, "security-suppressions-diff", "--base-ref", "origin/main")
    assert result.returncode == 2, (
        f"expected exit 2 on a grafted clone, got {result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "complete Git history" in result.stderr


def test_suppression_range_refuses_to_measure_a_grafted_clone(
    graftable_clone: tuple[Path, Path],
) -> None:
    """The sibling range entrypoint shares the defect and the remedy.

    `check_range_suppressions` resolves its range through `git merge-base` and
    falls back to the base tip when that fails, which is exactly what a graft
    causes, so its range silently widened rather than erroring.
    """
    origin, clone = graftable_clone
    baseline = _run_policy(
        clone, "security-suppressions-range", "--base", "origin/main", "--head", "HEAD"
    )
    assert baseline.returncode == 0, baseline.stderr

    assert _git(clone, "fetch", "--depth=1", str(origin), "main").returncode == 0

    result = _run_policy(
        clone, "security-suppressions-range", "--base", "origin/main", "--head", "HEAD"
    )
    assert result.returncode == 2, (
        f"expected exit 2 on a grafted clone, got {result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "complete Git history" in result.stderr


def test_a_depth_limited_fetch_really_does_graft_a_complete_clone(
    graftable_clone: tuple[Path, Path],
) -> None:
    """Pins the premise the other tests and the workflow comments rest on.

    If a future git release stopped writing `.git/shallow` for this fetch, the
    guards above would still pass while guarding nothing, and the workflow
    comments would be wrong. This fails first and names why.
    """
    origin, clone = graftable_clone
    assert not (clone / ".git" / "shallow").exists()

    assert _git(clone, "fetch", "--depth=1", str(origin), "main").returncode == 0
    assert (clone / ".git" / "shallow").is_file()

    plain = _git(clone, "fetch", str(origin), "main")
    assert plain.returncode == 0, plain.stderr
    assert (clone / ".git" / "shallow").is_file(), (
        "a plain fetch removed the graft, so the workflow comments claiming a "
        "later full fetch cannot repair it are now wrong"
    )

    assert _git(clone, "fetch", "--unshallow", str(origin)).returncode == 0
    assert not (clone / ".git" / "shallow").exists()


