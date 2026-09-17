"""Real-git regression: an untracked file survives the actual autofix git flow.

Issue #4790, acceptance criterion 4: "Add a regression test using a sentinel
untracked file across commit, merge, test, and push workflows."

``test_untracked_file_preservation.py`` (PR #5556) proves the autofix surfaces
never *contain* a verb capable of destroying an untracked file. It is a text
scan: it cannot prove that the verbs those surfaces DO use (checkout, merge,
merge --abort, push) leave an operator-owned untracked file alone when they
actually run. This file closes that gap. It drives
``resolve_conflicts_runner()``, the exact production function the issue's
auto-generated PRD comment accused (and PR #5556's investigation cleared),
against a real git repository with a real bare "origin" remote, with an
untracked sentinel file present throughout every case:

- a clean merge that reaches the push step,
- a merge that conflicts on a non-auto-resolvable file and runs
  ``git merge --abort``,
- a checkout that git itself refuses because the target branch tracks the
  same path the sentinel occupies untracked (the collision case from the
  investigation comment on #4790).

Each case asserts the sentinel is byte-identical afterward and still reported
as untracked (or, in the collision case, that the branch never switched).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_skills_import import import_skill_script

from tests.gc_real_git import GitSandbox, git, write_and_commit

mod = import_skill_script(".claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py")
resolve_conflicts_runner = mod.resolve_conflicts_runner

_SENTINEL = "sentinel.txt"
_SENTINEL_CONTENT = "operator-owned, unrelated to this PR\n"


def _untracked_status(sandbox: GitSandbox) -> str:
    return git(sandbox.main, "status", "--porcelain").stdout


def _current_branch(sandbox: GitSandbox) -> str:
    return git(sandbox.main, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def _make_feature_branch(sandbox: GitSandbox) -> None:
    """Branch "feature" off "main", each side committing a different file."""
    git(sandbox.main, "checkout", "-b", "feature")
    write_and_commit(sandbox.main, "feature.txt", "feature work\n", "feature commit")
    git(sandbox.main, "push", "-u", "origin", "feature")
    git(sandbox.main, "checkout", "main")
    write_and_commit(sandbox.main, "main-change.txt", "main work\n", "main commit")
    git(sandbox.main, "push", "origin", "main")


def _drop_sentinel(sandbox: GitSandbox, content: str = _SENTINEL_CONTENT) -> Path:
    """Create an untracked sentinel file. Never staged, never committed."""
    path = sandbox.main / _SENTINEL
    path.write_text(content, encoding="utf-8")
    return path


def test_clean_merge_preserves_untracked_sentinel_through_push(
    git_sandbox: GitSandbox, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checkout + a clean auto-merge + push must not touch an untracked file."""
    _make_feature_branch(git_sandbox)
    sentinel = _drop_sentinel(git_sandbox)

    monkeypatch.chdir(git_sandbox.main)
    result = resolve_conflicts_runner(branch_name="feature", target_branch="main")

    # success is only ever set True after `git push` returns 0 (production
    # code, resolve_pr_conflicts.py), so this also proves the push happened.
    assert result["success"] is True, result["message"]
    assert sentinel.read_text(encoding="utf-8") == _SENTINEL_CONTENT
    assert f"?? {_SENTINEL}" in _untracked_status(git_sandbox)

    # A "clean merge" claim with no merge commit and no push is a no-op that
    # accidentally satisfies the assertions above (the branch is unchanged, a
    # no-op push exits 0). Prove the merge and the push each actually ran.
    assert git(git_sandbox.main, "rev-parse", "HEAD^2", check=False).returncode == 0, (
        "no merge commit: the merge leg never ran"
    )
    head_sha = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    remote_feature = git(git_sandbox.main, "ls-remote", "origin", "refs/heads/feature").stdout
    assert head_sha in remote_feature, "merge commit never reached origin: the push did not land"


def test_conflicting_merge_aborts_and_preserves_untracked_sentinel(
    git_sandbox: GitSandbox, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blocked, non-auto-resolvable conflict runs `merge --abort` cleanly."""
    git(git_sandbox.main, "checkout", "-b", "feature")
    write_and_commit(git_sandbox.main, "src/app.py", "feature version\n", "feature app.py")
    git(git_sandbox.main, "push", "-u", "origin", "feature")
    git(git_sandbox.main, "checkout", "main")
    write_and_commit(git_sandbox.main, "src/app.py", "main version\n", "main app.py")
    git(git_sandbox.main, "push", "origin", "main")

    sentinel = _drop_sentinel(git_sandbox)

    monkeypatch.chdir(git_sandbox.main)
    result = resolve_conflicts_runner(branch_name="feature", target_branch="main")

    assert result["success"] is False
    assert "src/app.py" in result["message"]
    assert sentinel.read_text(encoding="utf-8") == _SENTINEL_CONTENT
    # merge --abort must leave nothing behind except the untracked sentinel:
    # no conflict markers, no half-merged index, no stray files.
    assert _untracked_status(git_sandbox) == f"?? {_SENTINEL}\n"
    assert _current_branch(git_sandbox) == "feature"


def test_checkout_refuses_rather_than_overwrites_a_colliding_untracked_file(
    git_sandbox: GitSandbox, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reproduces the collision case from the #4790 investigation comment.

    ``feature`` tracks a file at the same path the sentinel occupies
    untracked on ``main``. Git must refuse the checkout rather than delete or
    silently overwrite the operator's file, and the caller's own
    ``if r.returncode != 0: return result`` must stop there.
    """
    git(git_sandbox.main, "checkout", "-b", "feature")
    write_and_commit(git_sandbox.main, _SENTINEL, "tracked-version\n", "feature tracks sentinel")
    git(git_sandbox.main, "push", "-u", "origin", "feature")
    git(git_sandbox.main, "checkout", "main")

    sentinel = _drop_sentinel(git_sandbox, content="operator-owned-2\n")

    monkeypatch.chdir(git_sandbox.main)
    result = resolve_conflicts_runner(branch_name="feature", target_branch="main")

    assert result["success"] is False
    assert "Failed to checkout branch feature" in result["message"]
    assert sentinel.read_text(encoding="utf-8") == "operator-owned-2\n"
    assert _current_branch(git_sandbox) == "main"
