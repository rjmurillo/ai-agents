"""Real git regression tests for stale worktree entries.

A stale entry is one whose working directory is gone while its admin record
survives. That record can hold three independent things nothing else holds:
a detached HEAD no ref contains, blobs staged in its orphaned index, and
commits its reflog anchors that are not ancestors of HEAD. Rescuing one
rescues none of the others.

Mocks cannot prove this. Whether ``git for-each-ref --contains`` finds a
commit, whether git sets ``prunable`` on a locked entry, and whether the
printed recovery commands actually recover anything are all facts about git.
So these tests build the loss with real git and then read the report back.

The merge-status cases live in ``test_gc_worktrees_real_git.py``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.maintenance import _gc_apply, _gc_stale, gc_worktrees, worktree_report
from tests.gc_real_git import (
    GitSandbox,
    decision_for,
    git,
    run_gc_json,
    write_and_commit,
)


def _add_worktree_branch(sandbox: GitSandbox, branch: str) -> Path:
    worktree = sandbox.root / branch.replace("/", "-")
    git(sandbox.main, "worktree", "add", "-b", branch, str(worktree))
    return worktree


def _create_squash_merged_branch(sandbox: GitSandbox, branch: str = "feat/squash") -> Path:
    worktree = _add_worktree_branch(sandbox, branch)
    write_and_commit(worktree, "feature.txt", f"{branch}\n", "feature")
    git(worktree, "push", "-u", "origin", branch)
    git(sandbox.main, "merge", "--squash", branch)
    git(sandbox.main, "commit", "-m", "squash feature")
    git(sandbox.main, "push", "origin", "main")
    git(sandbox.main, "push", "origin", f":{branch}")
    git(sandbox.main, "fetch", "--prune", "origin")
    return worktree


def _make_stale_worktree(sandbox: GitSandbox, branch: str) -> tuple[Path, str]:
    """Register a worktree, commit in it, then delete the directory."""
    worktree = _add_worktree_branch(sandbox, branch)
    write_and_commit(worktree, "work.txt", f"{branch}\n", "work")
    head = git(worktree, "rev-parse", "HEAD").stdout.strip()
    shutil.rmtree(worktree)
    return worktree, head


def test_a_stale_entry_is_kept_not_reported_as_an_inspection_failure(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The plan must name a stale entry and hold it, not fail to read it."""
    worktree, _ = _make_stale_worktree(git_sandbox, "feat/stale")

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = decision_for(report, worktree)
    assert decision["remove"] is False
    assert decision["reason"] == worktree_report.KEEP_STALE


def test_the_report_warns_when_clearing_would_destroy_staged_work(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End to end: real staged blob, real orphaned index, real report text."""
    worktree = _add_worktree_branch(git_sandbox, "feat/staged-report")
    write_and_commit(worktree, "work.txt", "committed\n", "work")
    (worktree / "staged.txt").write_text("only staged\n", encoding="utf-8")
    git(worktree, "add", "staged.txt")
    shutil.rmtree(worktree)

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = decision_for(report, worktree)
    assert decision["remove"] is False
    reason = decision["reason"]
    assert isinstance(reason, str)
    assert "WARNING" in reason, reason
    assert "checkout-index" in reason, reason


def test_the_report_stays_quiet_when_the_orphaned_index_is_clean(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Negative control: a warning on every stale entry would be noise."""
    worktree, _ = _make_stale_worktree(git_sandbox, "feat/clean-index")

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    reason = decision_for(report, worktree)["reason"]
    assert reason == worktree_report.KEEP_STALE


def test_the_warning_survives_being_run_from_a_subdirectory(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """git answers ``--git-common-dir`` relatively, so the lookup needs an anchor.

    Run from the repository root it says ``.git``; from a subdirectory,
    ``../.git``. Resolving either against the process directory rather than the
    main worktree loses the admin directory, and losing it drops the warning
    without a word.
    """
    worktree = _add_worktree_branch(git_sandbox, "feat/subdir-warning")
    write_and_commit(worktree, "work.txt", "committed\n", "work")
    (worktree / "staged.txt").write_text("only staged\n", encoding="utf-8")
    git(worktree, "add", "staged.txt")
    shutil.rmtree(worktree)
    nested = git_sandbox.main / "deep" / "nested"
    nested.mkdir(parents=True)

    monkeypatch.chdir(nested)
    assert gc_worktrees.main(["--json"]) == 0
    report = json.loads(capsys.readouterr().out)

    reason = decision_for(report, worktree)["reason"]
    assert isinstance(reason, str)
    assert "WARNING" in reason, reason


def test_a_moved_worktree_is_marked_prunable_yet_still_works(
    git_sandbox: GitSandbox,
) -> None:
    """Why stale entries are kept: git cannot tell deleted from moved.

    A worktree that was moved rather than deleted carries the identical
    ``prunable gitdir file points to non-existent location`` marker while
    remaining a fully functional checkout. Removing its admin record on the
    strength of that marker breaks a live worktree, so the marker alone can
    never authorize removal. That is a claim about git itself, so it is pinned
    against real git rather than a mock.
    """
    worktree = _add_worktree_branch(git_sandbox, "feat/moved")
    write_and_commit(worktree, "work.txt", "moved\n", "work")
    relocated = git_sandbox.root / "relocated"
    worktree.rename(relocated)

    listing = git(git_sandbox.main, "worktree", "list", "--porcelain").stdout
    assert "prunable" in listing

    still_alive = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=relocated,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert still_alive.returncode == 0, still_alive.stderr


def test_removing_a_stale_entry_would_drop_staged_content(
    git_sandbox: GitSandbox,
) -> None:
    """The loss the keep-stale decision prevents, demonstrated end to end.

    ``git add`` writes a blob into the object database and records it in the
    worktree's own index. Deleting the directory leaves that index behind, and
    ``git worktree remove`` then accepts the entry and takes the index with it.
    The blob survives only until the next gc, and nothing references it.
    """
    worktree = _add_worktree_branch(git_sandbox, "feat/staged")
    (worktree / "staged.txt").write_text("only staged\n", encoding="utf-8")
    git(worktree, "add", "staged.txt")
    blob = git(worktree, "rev-parse", ":staged.txt").stdout.strip()
    admin = Path(git(worktree, "rev-parse", "--git-dir").stdout.strip())
    shutil.rmtree(worktree)

    def staged_paths() -> str:
        return subprocess.run(
            ["git", "ls-files", "--stage"],
            cwd=git_sandbox.main,
            env={**os.environ, "GIT_INDEX_FILE": str(admin / "index")},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout

    assert blob in staged_paths(), "before removal the orphaned index still names the blob"
    assert blob not in git(git_sandbox.main, "rev-list", "--objects", "--all").stdout, (
        "the index is the only anchor; no ref reaches the blob"
    )

    subprocess.run(
        ["git", "worktree", "remove", str(worktree)],
        cwd=git_sandbox.main,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert not (admin / "index").exists(), "removal took the last anchor with it"
    assert blob not in staged_paths()


def test_apply_drives_real_git_and_really_removes_the_worktree(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production apply, real git, no mocks between them.

    Every other apply test mocks ``remove_worktree``, so a no-op body would
    pass them all. This one runs ``build_report`` and ``apply_removals`` in the
    sandbox and asserts against git's own listing afterwards.
    """
    worktree = _add_worktree_branch(git_sandbox, "feat/merged")
    write_and_commit(worktree, "feature.txt", "merged\n", "feature")
    git(worktree, "push", "-u", "origin", "feat/merged")
    git(git_sandbox.main, "merge", "--no-ff", "-m", "merge", "feat/merged")
    git(git_sandbox.main, "push", "origin", "main")
    git(git_sandbox.main, "fetch", "origin")

    monkeypatch.chdir(git_sandbox.main)
    report = gc_worktrees.build_report("origin/main", apply=True)
    assert [d.path for d in report.candidates] == [str(worktree)], [
        (d.path, d.reason) for d in report.decisions
    ]

    _gc_apply.apply_removals(
        report,
        revalidate=lambda: gc_worktrees.build_report("origin/main", apply=True),
        run_git=gc_worktrees._run_git,
    )

    assert report.remove_errors == []
    assert report.removed == [str(worktree)]
    assert not worktree.exists()
    remaining = git(git_sandbox.main, "worktree", "list", "--porcelain").stdout
    assert str(worktree) not in remaining


def test_apply_leaves_a_worktree_that_changed_after_the_plan(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The TOCTOU window, closed and proven against real git.

    Without revalidation this removes a worktree that picked up unpushed work
    between the plan and the apply. ``git worktree remove`` refuses a dirty
    tree but accepts a committed one, so the tree is left clean here on
    purpose: a mocked remover could not tell the difference.
    """
    worktree = _add_worktree_branch(git_sandbox, "feat/racy")
    write_and_commit(worktree, "feature.txt", "racy\n", "feature")
    git(worktree, "push", "-u", "origin", "feat/racy")
    git(git_sandbox.main, "merge", "--no-ff", "-m", "merge", "feat/racy")
    git(git_sandbox.main, "push", "origin", "main")
    git(git_sandbox.main, "fetch", "origin")

    monkeypatch.chdir(git_sandbox.main)
    report = gc_worktrees.build_report("origin/main", apply=True)
    assert [d.path for d in report.candidates] == [str(worktree)]

    write_and_commit(worktree, "late.txt", "after the plan\n", "late work")
    late = git(worktree, "rev-parse", "HEAD").stdout.strip()

    _gc_apply.apply_removals(
        report,
        revalidate=lambda: gc_worktrees.build_report("origin/main", apply=True),
        run_git=gc_worktrees._run_git,
    )

    assert report.removed == []
    assert worktree.exists()
    assert any(str(worktree) in e for e in report.remove_errors), report.remove_errors
    assert git(git_sandbox.main, "cat-file", "-t", late).stdout.strip() == "commit"


def test_the_report_warns_when_a_reflog_only_commit_would_be_orphaned(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A detached worktree that commits and then moves off leaves no ref behind.

    The worktree-local reflog is the sole anchor. ``for-each-ref --contains``
    cannot see it, because *current* HEAD is reachable. Clearing the entry
    deletes the reflog and the commit becomes garbage.
    """
    head = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "detached-reflog"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)
    write_and_commit(worktree, "orphan.txt", "only in the reflog\n", "abandoned")
    orphan = git(worktree, "rev-parse", "HEAD").stdout.strip()
    git(worktree, "checkout", "--detach", head)
    shutil.rmtree(worktree)

    assert git(git_sandbox.main, "for-each-ref", "--contains", orphan).stdout == ""

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = decision_for(report, worktree)
    assert decision["remove"] is False
    reason = decision["reason"]
    assert isinstance(reason, str)
    assert "WARNING" in reason, reason
    assert "git -C " in reason, reason
    assert f"branch gc-rescue-{orphan} {orphan}" in reason, reason


def test_the_report_stays_quiet_when_the_reflog_holds_nothing_unreachable(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Negative control: a branched worktree's reflog entries are all reachable."""
    worktree = _add_worktree_branch(git_sandbox, "feat/reachable-reflog")
    write_and_commit(worktree, "kept.txt", "on a branch\n", "kept")
    shutil.rmtree(worktree)

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    reason = decision_for(report, worktree)["reason"]
    assert isinstance(reason, str)
    assert "gc-rescue-" not in reason, reason


def test_a_locked_stale_entry_still_reports_its_staged_work(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The lock is temporary; the orphaned index outlives it."""
    worktree = _add_worktree_branch(git_sandbox, "feat/locked-stale")
    write_and_commit(worktree, "work.txt", "committed\n", "work")
    (worktree / "staged.txt").write_text("only staged\n", encoding="utf-8")
    git(worktree, "add", "staged.txt")
    git(git_sandbox.main, "worktree", "lock", str(worktree))
    shutil.rmtree(worktree)

    report = run_gc_json(git_sandbox, monkeypatch, capsys)
    reason = decision_for(report, worktree)["reason"]
    assert isinstance(reason, str)
    assert "locked" in reason, reason
    assert "checkout-index" in reason, reason


def test_a_worktree_moved_onto_another_s_old_path_does_not_make_it_healthy(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The marker is there, and it belongs to somebody else.

    Delete worktree A, move worktree B onto A's path, and A's directory holds
    a ``.git`` file again. Checking that the marker exists calls A healthy, so
    every probe that follows reads B's admin record and reports it as A's:
    B's index, B's reflog, B's HEAD. A's own staged work is then invisible.
    """
    victim = _add_worktree_branch(git_sandbox, "feat/victim")
    (victim / "staged.txt").write_text("only staged\n", encoding="utf-8")
    git(victim, "add", "staged.txt")
    squatter = _add_worktree_branch(git_sandbox, "feat/squatter")

    shutil.rmtree(victim)
    shutil.move(str(squatter), str(victim))
    assert (victim / ".git").is_file(), "the moved worktree brought its marker along"

    report = run_gc_json(git_sandbox, monkeypatch, capsys)
    reason = decision_for(report, victim)["reason"]
    assert isinstance(reason, str)
    assert decision_for(report, victim)["remove"] is False
    assert "stale admin entry" in reason, reason
    assert "checkout-index" in reason, "the victim's staged work must still be named"


def test_a_standalone_repository_replacing_a_linked_path_is_kept_not_removed(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A real repository dropped onto a stale entry's path is foreign, so it is kept.

    Delete a linked worktree and initialise a standalone repository at the same
    path. A linked checkout carries a ``.git`` file holding ``gitdir:``; a
    standalone repository carries a ``.git`` directory. Reading that directory
    as the registered checkout would let the merged-and-clean path reach
    ``git worktree remove``, which names the path and would delete the
    standalone repository together with its object database. Treating a ``.git``
    directory as foreign keeps the entry stale instead, so the commit only this
    repository holds stays reachable. The main worktree, whose ``.git`` is also
    a directory, never arrives here: ``decide`` returns ``KEEP_MAIN`` for it.
    """
    worktree = _add_worktree_branch(git_sandbox, "feat/replaced")
    shutil.rmtree(worktree)

    # A real standalone repository now sits where the linked checkout was, with
    # a commit no other repository holds. Its identity is set locally because the
    # sandbox configures the author only on ``main``.
    git(git_sandbox.main, "init", str(worktree))
    git(worktree, "config", "user.email", "foreign@example.com")
    git(worktree, "config", "user.name", "Foreign Repo")
    git(worktree, "config", "commit.gpgsign", "false")
    foreign_commit = write_and_commit(worktree, "unrelated.txt", "not ours\n", "unrelated repo")
    assert (worktree / ".git").is_dir(), "git init writes a .git directory, not a gitdir file"

    # The core of the fix, read against a real standalone repository: a ``.git``
    # directory here is foreign, not the registered checkout. This is the
    # assertion that fails if the ``IsADirectoryError`` branch goes back to
    # reporting the directory as present, which is what opened the deletion path.
    assert _gc_stale.linked_checkout_present(str(worktree)) is False

    decision = decision_for(run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    assert decision["remove"] is False, decision["reason"]

    # The decision leaves the standalone repository and its object database
    # untouched: the ``.git`` directory survives and the commit only it holds is
    # still resolvable there.
    assert (worktree / ".git").is_dir()
    assert git(worktree, "rev-parse", "HEAD").stdout.strip() == foreign_commit


def test_an_admin_record_overwritten_by_a_file_is_not_an_empty_one(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``ENOTDIR`` is corruption, and corruption is not "nothing staged".

    Replacing the admin directory's ``logs`` subtree with a regular file makes
    every ``stat`` under it raise ``NotADirectoryError``. Reading that as
    absence reports a clean, reflog-free entry for a record that has been
    damaged, which is the state most likely to be hiding something.
    """
    worktree = _add_worktree_branch(git_sandbox, "feat/enotdir")
    write_and_commit(worktree, "work.txt", "committed\n", "work")
    admin = git_sandbox.main / ".git" / "worktrees" / "feat-enotdir"
    shutil.rmtree(worktree)
    shutil.rmtree(admin / "logs")
    (admin / "logs").write_text("not a directory\n", encoding="utf-8")

    report = run_gc_json(git_sandbox, monkeypatch, capsys)
    decision = decision_for(report, worktree)
    reason = decision["reason"]
    assert isinstance(reason, str)
    assert decision["remove"] is False
    assert "admin directory could not be read" in reason, reason
