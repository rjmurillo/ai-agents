"""Real-git coverage for worktrees sitting in the middle of a git operation.

Every other guard on the removal path reads either the working tree or the
object graph. An interrupted merge, cherry-pick, revert, bisect, or rebase is
recorded in neither. Git writes a pseudo-ref inside the worktree's own admin
directory, and that directory is exactly what the removal deletes, so the
commits the operation holds become unreachable at the moment the entry is
cleared. These tests build each operation with real git and assert the tool
refuses.

The merge case is the sharpest and is why this file exists: a merge whose
result matches the current tree leaves ``git status --porcelain`` completely
empty, so the dirty check, the HEAD comparison, and the reflog re-probe all
report a clean, merged, safe-to-remove worktree while ``MERGE_HEAD`` holds a
commit nothing else in the repository reaches.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.maintenance import _gc_anchors, _gc_stale
from tests.gc_real_git import GitSandbox, decision_for, git, run_gc_json, write_and_commit

# ``os.geteuid`` is itself absent on Windows, and root defeats a mode-based
# barrier, so the unreadable-directory case can only be built where both hold.
_NO_PERMISSION_BARRIER = os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0)


def _detached_worktree(sandbox: GitSandbox, name: str) -> Path:
    """A worktree detached at the tip of the main branch, merged and pushed."""
    worktree = sandbox.root / name
    git(sandbox.main, "worktree", "add", "--detach", str(worktree), "HEAD")
    return worktree


def _orphan_parent(worktree: Path) -> str:
    """A commit reachable from nothing, built without touching any ref.

    ``commit-tree`` writes no reflog entry and moves no ref, so the object it
    creates is anchored only by whatever the caller does with the id. That is
    what makes it the honest stand-in for the side of a merge a reader fetched
    and has not merged yet.
    """
    return git(worktree, "commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m", "orphan").stdout.strip()


def test_an_interrupted_merge_that_leaves_no_diff_is_still_refused(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The loss channel in full: porcelain empty, HEAD unmoved, MERGE_HEAD loaded.

    Reproduced against real git 2.43.0 before the guard existed. ``build_report``
    answered ``remove=True`` with the reason ``merged to base``, ``apply_removals``
    removed the worktree without a single error, and ``git fsck --unreachable``
    then listed the merge's other parent. Nothing in the run mentioned it.
    """
    worktree = _detached_worktree(git_sandbox, "mid-merge")
    other = _orphan_parent(worktree)
    git(worktree, "merge", "--no-commit", "--no-ff", other, check=False)

    assert git(worktree, "status", "--porcelain").stdout == "", (
        "this test is only meaningful while the porcelain output stays empty"
    )
    assert git(worktree, "rev-parse", "MERGE_HEAD").stdout.strip() == other

    decision = decision_for(run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    assert decision["remove"] is False, decision["reason"]
    assert "unfinished merge" in str(decision["reason"])


def test_the_commit_an_interrupted_merge_holds_is_reachable_from_nothing_else(
    git_sandbox: GitSandbox,
) -> None:
    """Why the refusal is worth a subprocess-free probe on the decision path.

    Asks git directly whether anything besides the pseudo-ref reaches the
    commit. If some other ref did, losing the admin directory would cost
    nothing and this guard would be ceremony.
    """
    worktree = _detached_worktree(git_sandbox, "unreachable-side")
    other = _orphan_parent(worktree)
    git(worktree, "merge", "--no-commit", "--no-ff", other, check=False)

    reaching = git(git_sandbox.main, "rev-list", "--all", "--reflog").stdout.split()
    assert other not in reaching, "the merge's other parent is anchored only by MERGE_HEAD"


@pytest.mark.parametrize(
    ("name", "marker", "expected"),
    [
        ("MERGE_HEAD", "MERGE_HEAD", "an unfinished merge is running"),
        ("CHERRY_PICK_HEAD", "CHERRY_PICK_HEAD", "an unfinished cherry-pick is running"),
        ("REVERT_HEAD", "REVERT_HEAD", "an unfinished revert is running"),
        ("BISECT_LOG", "BISECT_LOG", "an unfinished bisect is running"),
        ("rebase-merge", "rebase-merge", "an unfinished rebase is running"),
        ("rebase-apply", "rebase-apply", "an unfinished rebase is running"),
        ("sequencer", "sequencer", "an unfinished sequencer run is waiting"),
        ("index.lock", "index.lock", "another git process is holding the index lock"),
        ("HEAD.lock", "HEAD.lock", "another git process is updating HEAD"),
    ],
)
def test_every_operation_marker_git_can_write_is_recognised(
    git_sandbox: GitSandbox,
    name: str,
    marker: str,
    expected: str,
) -> None:
    """Each marker is read from the admin directory git actually uses.

    The marker is placed rather than produced by driving the operation, because
    the point under test is the lookup, not git's bookkeeping, and two of these
    (``rebase-apply``, ``sequencer``) need a conflict sequence to appear at all.
    ``test_a_real_interrupted_rebase_is_refused`` covers the produced case, and
    ``admin_dir_from_marker`` is asserted against git's own answer below, so
    neither this test nor that one stands on a hand-built layout alone.
    """
    worktree = _detached_worktree(git_sandbox, f"marker-{name.lower().replace('_', '-')}")
    admin = _gc_stale.admin_dir_from_marker(str(worktree))
    assert admin is not None
    (admin / marker).write_text("placeholder\n", encoding="utf-8")

    assert _gc_stale.in_progress_operation(str(worktree)) == expected


def test_the_admin_directory_the_probe_reads_is_the_one_git_names(
    git_sandbox: GitSandbox,
) -> None:
    """Revert-proofs the marker lookup against a hand-built path assumption.

    Every marker test above writes into whatever ``admin_dir_from_marker``
    returns, so a wrong answer there would make all of them pass against a
    directory git never reads. This pins it to ``git rev-parse``.
    """
    worktree = _detached_worktree(git_sandbox, "admin-identity")
    probed = _gc_stale.admin_dir_from_marker(str(worktree))
    assert probed is not None
    recorded = git(worktree, "rev-parse", "--absolute-git-dir").stdout.strip()
    assert probed.resolve() == Path(recorded).resolve()


def test_a_real_interrupted_rebase_is_refused(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A conflicted rebase driven through git, not a placed file."""
    worktree = git_sandbox.root / "mid-rebase"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), "HEAD")
    git(worktree, "checkout", "-b", "gc-rebase-side")
    write_and_commit(worktree, "clash.txt", "side\n", "side")
    git(worktree, "checkout", "--detach", "HEAD~1")
    write_and_commit(worktree, "clash.txt", "trunk\n", "trunk")
    rebase = git(worktree, "rebase", "gc-rebase-side", check=False)
    assert rebase.returncode != 0, "the rebase has to stop for a marker to exist"

    assert _gc_stale.in_progress_operation(str(worktree)) == "an unfinished rebase is running"
    decision = decision_for(run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    assert decision["remove"] is False, decision["reason"]


def test_a_worktree_with_no_operation_running_is_not_refused(
    git_sandbox: GitSandbox,
) -> None:
    """The negative control: an ordinary worktree answers None.

    Without this, a probe that returned a description unconditionally would
    satisfy every other test in the file and keep every worktree forever.
    """
    worktree = _detached_worktree(git_sandbox, "idle")
    assert _gc_stale.in_progress_operation(str(worktree)) is None


def test_an_unresolvable_checkout_answers_none_rather_than_refusing(
    git_sandbox: GitSandbox,
    tmp_path: Path,
) -> None:
    """A path with no ``.git`` marker is the stale case, which is decided elsewhere.

    Answering "an operation is running" here would keep every unreadable entry
    forever, which is the failure the stale diagnostics exist to avoid.
    """
    assert _gc_stale.in_progress_operation(str(tmp_path)) is None
    assert _gc_stale.admin_dir_from_marker(str(tmp_path)) is None


def test_a_marker_that_cannot_be_stated_withholds_rather_than_clearing(
    git_sandbox: GitSandbox,
) -> None:
    """A permission or I/O error on a marker is unknown, and unknown withholds.

    ``exists`` reads a missing marker and an unreadable one as the same
    ``False``, so a permission or I/O error on the admin directory would answer
    "no operation running" and let the entry be removed mid-flight. ``lstat``
    separates them: a ``FileNotFoundError`` is the ordinary "marker absent" and
    moves on, while any other ``OSError`` is disclosed as a reason that keeps
    the entry. Asserted with a real admin directory so the resolution the probe
    depends on is not itself mocked away.
    """
    worktree = _detached_worktree(git_sandbox, "unreadable-marker")
    with patch.object(Path, "lstat", side_effect=PermissionError(13, "denied")):
        result = _gc_stale.in_progress_operation(str(worktree))
    assert result is not None, "an unreadable marker must not read as no operation running"
    assert "could not be read" in result


def test_the_probe_costs_no_subprocess(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It runs once per worktree inside a time budget already holding three git calls.

    A subprocess here would be a fourth, so the cost is pinned rather than
    described.
    """
    worktree = _detached_worktree(git_sandbox, "no-subprocess")

    def _refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the operation probe must not shell out")

    monkeypatch.setattr(subprocess, "run", _refuse)
    assert _gc_stale.in_progress_operation(str(worktree)) is None


def test_a_locked_index_is_refused_because_git_would_remove_it_anyway(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """git worktree remove ignores index.lock, so the refusal has to come from here.

    Confirmed against real git 2.43.0: with the lock in place the removal
    succeeds, exits 0, and prints no warning, which means a commit being written
    at that moment goes with the directory. Asserted below rather than described,
    because a future git that started honouring the lock would make this guard
    redundant and the assertion is what would say so.
    """
    worktree = _detached_worktree(git_sandbox, "locked-index")
    admin = _gc_stale.admin_dir_from_marker(str(worktree))
    assert admin is not None
    (admin / "index.lock").write_text("", encoding="utf-8")

    decision = decision_for(run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    assert decision["remove"] is False, decision["reason"]
    assert "index lock" in str(decision["reason"])

    removal = git(git_sandbox.main, "worktree", "remove", str(worktree), check=False)
    assert removal.returncode == 0, "git still ignores the lock; drop this guard when it stops"
    assert not worktree.exists()


def test_a_head_lock_is_refused_because_git_would_remove_it_anyway(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """git writes HEAD.lock while it moves HEAD, and worktree remove ignores it.

    A detached-HEAD update writes ``HEAD`` directly, so ``HEAD.lock`` sits in
    the admin directory during that window while none of the operation markers
    exist. Confirmed against real git 2.43.0: with the lock in place the removal
    still succeeds, exits 0, and prints nothing, so a HEAD move in flight is
    interrupted silently unless this guard keeps the entry. The removal is
    asserted rather than described so a future git that honoured the lock would
    make this guard redundant and say so here.
    """
    worktree = _detached_worktree(git_sandbox, "locked-head")
    admin = _gc_stale.admin_dir_from_marker(str(worktree))
    assert admin is not None
    (admin / "HEAD.lock").write_text("", encoding="utf-8")

    decision = decision_for(run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    assert decision["remove"] is False, decision["reason"]
    assert "updating HEAD" in str(decision["reason"])

    removal = git(git_sandbox.main, "worktree", "remove", str(worktree), check=False)
    assert removal.returncode == 0, "git still ignores HEAD.lock; drop this guard when it stops"
    assert not worktree.exists()


def _worktree_ref_lock(worktree: Path, name: str = "installing") -> Path:
    """The path git's files backend locks while it installs ``refs/worktree/<name>``."""
    admin = _gc_stale.admin_dir_from_marker(str(worktree))
    assert admin is not None
    lock = admin / "refs" / "worktree" / f"{name}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    return lock


def test_a_held_worktree_ref_lock_is_refused_because_git_would_remove_it_anyway(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A ref lock one level down is the same loss as ``index.lock``, one level up.

    ``refs/worktree/*`` lives in the worktree's own admin directory, and the
    files backend writes ``<ref>.lock`` beside the ref while it installs one.
    Confirmed against real git 2.43.0: with the lock held the removal still
    succeeds, exits 0, and prints nothing, so the ref never lands and the commit
    it was about to anchor is left with nothing naming it.

    The lock is written empty here because that is the state the anchor readers
    cannot see, asserted below: a delete transaction holds an empty lock for its
    whole duration, and an update holds one between creation and the write.
    """
    worktree = _detached_worktree(git_sandbox, "locked-worktree-ref")
    lock = _worktree_ref_lock(worktree)
    lock.write_text("", encoding="utf-8")

    admin = _gc_stale.admin_dir_from_marker(str(worktree))
    assert admin is not None
    assert _gc_anchors.worktree_ref_oids(admin) == [], (
        "an empty lock names no object, so the anchor reader cannot be what keeps this entry"
    )

    decision = decision_for(run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    assert decision["remove"] is False, decision["reason"]
    assert "updating a worktree-local ref" in str(decision["reason"])

    removal = git(git_sandbox.main, "worktree", "remove", str(worktree), check=False)
    assert removal.returncode == 0, "git still ignores ref locks; drop this guard when it stops"
    assert not worktree.exists()


def test_the_lock_a_real_git_transaction_holds_is_the_one_this_probe_reads(
    git_sandbox: GitSandbox,
) -> None:
    """Revert-proofs the lock path against a hand-built layout.

    Every assertion above writes the lock itself, so a wrong path would make
    them pass against a file git never creates. This drives ``update-ref
    --stdin`` to a prepared transaction, which is exactly the window where git
    holds the lock and has not yet renamed it into place, and reads the probe
    while git is still holding it.
    """
    worktree = _detached_worktree(git_sandbox, "real-ref-transaction")
    target = _orphan_parent(worktree)
    transaction = subprocess.Popen(
        ["git", "update-ref", "--stdin"],
        cwd=worktree,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        assert transaction.stdin is not None
        assert transaction.stdout is not None
        transaction.stdin.write(f"start\nupdate refs/worktree/installing {target}\nprepare\n")
        transaction.stdin.flush()
        assert transaction.stdout.readline().strip() == "start: ok"
        assert transaction.stdout.readline().strip() == "prepare: ok"

        assert _worktree_ref_lock(worktree).exists(), "git locks a path this probe does not read"
        assert (
            _gc_stale.in_progress_operation(str(worktree))
            == "another git process is updating a worktree-local ref"
        )
    finally:
        if transaction.stdin is not None and not transaction.stdin.closed:
            transaction.stdin.write("abort\n")
            transaction.stdin.close()
        transaction.wait(timeout=30)
        if transaction.stdout is not None:
            transaction.stdout.close()
        if transaction.stderr is not None:
            transaction.stderr.close()

    assert _gc_stale.in_progress_operation(str(worktree)) is None, (
        "the refusal must end with the transaction, or every worktree is kept forever"
    )


def test_a_worktree_local_ref_with_no_lock_is_not_refused(
    git_sandbox: GitSandbox,
) -> None:
    """The negative control: the ref itself is an anchor, not an operation.

    Without this, a probe that refused on the mere presence of ``refs/`` would
    satisfy the tests above and keep every worktree that ever held a
    per-worktree ref. Its commits are covered by ``worktree_ref_oids``, which is
    asserted here so the two probes are not confused for one another.
    """
    worktree = _detached_worktree(git_sandbox, "settled-worktree-ref")
    target = _orphan_parent(worktree)
    git(worktree, "update-ref", "refs/worktree/settled", target)

    admin = _gc_stale.admin_dir_from_marker(str(worktree))
    assert admin is not None
    assert _gc_anchors.worktree_ref_oids(admin) == [target]
    assert _gc_stale.in_progress_operation(str(worktree)) is None


@pytest.mark.skipif(_NO_PERMISSION_BARRIER, reason="requires a non-root POSIX permission barrier")
def test_unreadable_per_worktree_refs_withhold_rather_than_clearing(
    git_sandbox: GitSandbox,
) -> None:
    """An unreadable ``refs/`` is unknown, and unknown keeps the entry.

    A walk that cannot open the directory answers the same way it does for the
    anchor readers. Reading it as "no lock here" would be the silent all-clear
    every probe in this module exists to prevent.
    """
    worktree = _detached_worktree(git_sandbox, "unreadable-refs")
    refs = _worktree_ref_lock(worktree).parent.parent
    refs.chmod(0o000)
    try:
        result = _gc_stale.in_progress_operation(str(worktree))
    finally:
        refs.chmod(0o755)

    assert result is not None, "an unreadable refs directory must not read as nothing in flight"
    assert "could not be read" in result


def test_the_ref_lock_probe_costs_no_subprocess(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal path is subprocess-free too, not only the idle path.

    ``test_the_probe_costs_no_subprocess`` pins the cost of answering None. This
    pins the cost of answering with a refusal, which is the path that walks a
    directory rather than stopping at a ``stat``.
    """
    worktree = _detached_worktree(git_sandbox, "ref-lock-cost")
    _worktree_ref_lock(worktree).write_text("", encoding="utf-8")

    def _refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the operation probe must not shell out")

    monkeypatch.setattr(subprocess, "run", _refuse)
    assert (
        _gc_stale.in_progress_operation(str(worktree))
        == "another git process is updating a worktree-local ref"
    )
