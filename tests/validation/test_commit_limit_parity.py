"""Bidirectional parity tests for the commit-limit merge-detection predicate.

Issue #3997: CI and the pre-push hook used different predicates to decide
whether a branch qualifies for the 40-commit relief. The fix unifies them via
main_first_parent_shas in pr_commit_count.py.

Both gates must AGREE on every history:
- A branch that merges origin/main's trunk: BOTH grant the 40-commit relief.
- A branch that merges only a side branch (not on origin/main's trunk): BOTH
  deny the relief, keeping the 20-commit limit.

The tests here are the required bidirectional controls from the campaign
discipline: a history that should be relieved is tested through both paths,
and a history that should not be relieved is tested through both paths.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from scripts.validation import git_hook_policy as policy
from scripts.validation import pr_commit_count as commit_count

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=True,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "user@example.com")


def _commit(repo: Path, name: str) -> str:
    f = repo / f"{name}.md"
    f.write_text(f"{name}\n", encoding="utf-8")
    _git(repo, "add", "--", str(f.name))
    _git(repo, "commit", "-qm", f"test: {name}")
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _push_update_for_feature(repo: Path, base: str, head: str) -> policy.PushUpdate:
    src = policy.PushRef("refs/heads/feature", head, "refs/heads/feature", base)
    return policy.PushUpdate(src, base, head, f"{base}..{head}", "feature")


def _api_commits(repo: Path, head: str) -> list[Any]:
    """Simulate the GitHub API commit list for a PR.

    Uses origin/main..head to match what the real GitHub API returns:
    commits reachable from head but NOT from the base branch (origin/main).
    Each entry has the shape: {"sha": ..., "parents": [...]}.
    """
    result = _git(repo, "rev-list", "--topo-order", f"origin/main..{head}")
    shas = [s for s in result.stdout.splitlines() if s]
    commits = []
    for sha in shas:
        parents_raw = _git(repo, "log", "-1", "--format=%P", sha).stdout.strip()
        parents = [{"sha": p} for p in parents_raw.split() if p]
        commits.append({"sha": sha, "parents": parents})
    return commits


# ---------------------------------------------------------------------------
# Repo builders
# ---------------------------------------------------------------------------


def _repo_branch_merges_main(tmp_path: Path, name: str) -> tuple[Path, str, str]:
    """A feature branch that merges origin/main directly.

    History:
        main: base -> m1  [origin/main]
        feature: base -> f1 -> f2 -> merge(m1)

    m1 is on main's first-parent history. Both gates must grant relief.
    """
    repo = tmp_path / name
    _init_repo(repo)
    _commit(repo, "base")
    _git(repo, "branch", "feature")
    _commit(repo, "m1")
    main_tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", main_tip)
    _git(repo, "checkout", "-q", "feature")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _commit(repo, "f1")
    _commit(repo, "f2")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge main", "main")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, base, head


def _repo_branch_merges_landed_side(tmp_path: Path, name: str) -> tuple[Path, str, str]:
    """A feature branch that merges a side branch already landed on main.

    This is the divergence case from issue #3997.

    History:
        side: base -> s1
        main: base -> before -> merge_landing(s1) -> after  [origin/main]
        feature: base -> f1 -> f2 -> merge(s1)

    s1 is reachable from origin/main (via the non-first parent of merge_landing)
    but is NOT on origin/main's first-parent history.

    Pre-fix: CI granted relief (s1 is external to the PR commit list).
    Post-fix: CI denies relief (s1 not on first-parent trunk), matching the hook.
    Both gates must deny relief.
    """
    repo = tmp_path / name
    _init_repo(repo)
    base_sha = _commit(repo, "base")
    # Create side branch and add a commit to it.
    _git(repo, "branch", "side")
    _git(repo, "checkout", "-q", "side")
    _commit(repo, "s1")
    # Land the side branch on main via a merge commit.
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "before")
    _git(repo, "merge", "-q", "--no-ff", "-m", "land side on main", "side")
    _commit(repo, "after")
    main_tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", main_tip)
    # Create feature branch from base (before side was landed) and merge side.
    _git(repo, "checkout", "-q", "-b", "feature", base_sha)
    _commit(repo, "f1")
    _commit(repo, "f2")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge already-landed side branch", "side")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, base_sha, head


# ---------------------------------------------------------------------------
# Parity tests: both gates must agree
# ---------------------------------------------------------------------------


def test_both_gates_grant_relief_when_branch_merges_main(tmp_path: Path) -> None:
    """POSITIVE PARITY: a merge of origin/main grants relief in both gates.

    The 40-commit ceiling exists for this case. Both the pre-push hook and CI
    must grant relief, or the developer gets a contradictory governance signal.
    """
    repo, base, head = _repo_branch_merges_main(tmp_path, "both-grant")

    update = _push_update_for_feature(repo, base, head)
    api_commits = _api_commits(repo, head)

    hook_grants = policy._contains_main_merge(update, repo)
    ci_grants = commit_count.contains_main_merge(api_commits, repo)

    assert hook_grants is True, "pre-push hook must grant relief for a merge of main"
    assert ci_grants is True, "CI must grant relief for a merge of main"


def test_both_gates_deny_relief_when_branch_merges_only_landed_side(tmp_path: Path) -> None:
    """NEGATIVE PARITY (the divergence case from issue #3997).

    A feature branch that merges a side branch already landed on main must NOT
    receive the 40-commit relief from either gate. Before the fix, CI's
    contains_base_merge granted relief (s1 was external to the PR commit list
    because s1 is reachable from main), while the pre-push hook denied it (s1
    is not on origin/main's first-parent history).
    """
    repo, base, head = _repo_branch_merges_landed_side(tmp_path, "both-deny")

    update = _push_update_for_feature(repo, base, head)
    api_commits = _api_commits(repo, head)

    hook_grants = policy._contains_main_merge(update, repo)
    ci_grants = commit_count.contains_main_merge(api_commits, repo)

    assert hook_grants is False, (
        "pre-push hook must deny relief for a merge of a landed side branch"
    )
    assert ci_grants is False, (
        "CI must deny relief for a merge of a landed side branch (issue #3997)"
    )
