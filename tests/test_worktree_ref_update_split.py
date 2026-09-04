"""Real git regression tests for the ref-update split issue #4498 reported.

A linked worktree holds its own HEAD, index, and files, but the branch it has
checked out is an ordinary ref in the shared ref store. `git update-ref` is
plumbing and refuses nothing, so a writer in another worktree can move that ref
forward while the linked worktree's index and files stay on the old commit.
Git then answers `rev-parse HEAD` with the new commit and `write-tree` with the
old tree, and `git status` presents the whole difference as if the worktree's
owner had staged it.

Whether git actually behaves that way is a fact about git, not about this
repository's code, so these tests move a real ref in a real worktree and then
ask real git. Each positive assertion is paired with a control that fails when
the split is absent, so an assertion that stops detecting is caught rather than
passing silently.

Scope: issue #4498's acceptance criteria ask the correction queue to refuse or
repair this state. No correction queue exists in this repository, so these
tests pin the hazard rather than any queue behavior. They give a future
assignment preflight a falsifiable target: the third test shows the comparison
such a preflight cannot rely on.
"""

from __future__ import annotations

from pathlib import Path

from tests.gc_real_git import GitSandbox, git, write_and_commit


def _feature_worktree(sandbox: GitSandbox) -> tuple[Path, str]:
    """Check `feature` out in a linked worktree and return it with its commit."""
    commit_a = git(sandbox.main, "rev-parse", "HEAD").stdout.strip()
    git(sandbox.main, "branch", "feature", commit_a)
    worktree = sandbox.root / "feature-worktree"
    git(sandbox.main, "worktree", "add", str(worktree), "feature")
    return worktree, commit_a


def _tree_of(cwd: Path, commit: str) -> str:
    return git(cwd, "rev-parse", f"{commit}^{{tree}}").stdout.strip()


def test_update_ref_splits_a_linked_worktree_head_from_its_index(
    git_sandbox: GitSandbox,
) -> None:
    """Moving the checked-out branch ref leaves HEAD ahead of the index.

    This is issue #4498's minimal reproduction. `update-ref` is plumbing, so
    unlike `git branch -f` it does not refuse a branch checked out elsewhere.
    """
    worktree, commit_a = _feature_worktree(git_sandbox)
    commit_b = write_and_commit(git_sandbox.main, "b.txt", "b\n", "commit B")
    assert commit_b != commit_a

    git(git_sandbox.main, "update-ref", "refs/heads/feature", commit_b)

    assert git(worktree, "rev-parse", "HEAD").stdout.strip() == commit_b
    index_tree = git(worktree, "write-tree").stdout.strip()
    assert index_tree == _tree_of(worktree, commit_a), (
        "the index should still hold commit A's tree, which is the split"
    )
    assert index_tree != _tree_of(worktree, commit_b)
    assert git(worktree, "status", "--porcelain").stdout.strip() != "", (
        "git should present the A-to-B difference as pending work"
    )


def test_control_a_worktree_left_alone_keeps_head_and_index_agreeing(
    git_sandbox: GitSandbox,
) -> None:
    """Without the ref move, HEAD's tree and the index tree are the same object.

    The control for the test above. A worktree that reported a split here would
    mean the assertions are measuring ordinary worktree state rather than the
    damage `update-ref` does, and the positive case would prove nothing.
    """
    worktree, commit_a = _feature_worktree(git_sandbox)
    write_and_commit(git_sandbox.main, "b.txt", "b\n", "commit B")

    assert git(worktree, "rev-parse", "HEAD").stdout.strip() == commit_a
    assert git(worktree, "write-tree").stdout.strip() == _tree_of(worktree, commit_a)
    assert git(worktree, "status", "--porcelain").stdout.strip() == ""


def test_comparing_head_to_the_branch_ref_cannot_detect_the_split(
    git_sandbox: GitSandbox,
) -> None:
    """A preflight keyed on HEAD alone reports the split worktree as healthy.

    Issue #4498's second acceptance criterion asks an assignment preflight to
    compare the branch commit tree, the index tree, and the worktree state. This
    test is why all three are named: after the ref move, the linked worktree's
    HEAD and the branch ref agree exactly, so the cheapest check passes on the
    damaged worktree. Only the tree comparison separates them.
    """
    worktree, _ = _feature_worktree(git_sandbox)
    commit_b = write_and_commit(git_sandbox.main, "b.txt", "b\n", "commit B")
    git(git_sandbox.main, "update-ref", "refs/heads/feature", commit_b)

    worktree_head = git(worktree, "rev-parse", "HEAD").stdout.strip()
    branch_ref = git(git_sandbox.main, "rev-parse", "refs/heads/feature").stdout.strip()
    assert worktree_head == branch_ref, "the HEAD-only comparison agrees, and is therefore blind"
    assert git(worktree, "write-tree").stdout.strip() != _tree_of(worktree, branch_ref), (
        "the tree comparison is the one that separates them"
    )


def test_the_split_worktree_still_holds_content_a_reset_would_discard(
    git_sandbox: GitSandbox,
) -> None:
    """Files on disk stay on the old commit, so `reset --hard` is a data loss.

    Issue #4498's impact section: a reset or checkout used as routine recovery
    discards work the worktree still owns. The edge case is a path the newer
    commit deleted, because the file is present on disk while HEAD says it
    should not exist, and no ordinary reachability query names its content.
    """
    worktree, commit_a = _feature_worktree(git_sandbox)
    doomed = worktree / "only-in-a.txt"
    doomed.write_text("work that predates the ref move\n", encoding="utf-8")
    git(worktree, "add", "only-in-a.txt")
    git(worktree, "commit", "-m", "commit A-prime with a file B will not have")
    commit_a_prime = git(worktree, "rev-parse", "HEAD").stdout.strip()
    assert commit_a_prime != commit_a

    commit_b = write_and_commit(git_sandbox.main, "b.txt", "b\n", "commit B")
    git(git_sandbox.main, "update-ref", "refs/heads/feature", commit_b)

    assert doomed.read_text(encoding="utf-8") == "work that predates the ref move\n"
    assert git(worktree, "rev-parse", "HEAD").stdout.strip() == commit_b
    listed = git(worktree, "ls-tree", "--name-only", commit_b).stdout.split()
    assert "only-in-a.txt" not in listed, (
        "HEAD no longer lists the file, so a hard reset would remove it from disk"
    )
