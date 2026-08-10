"""Real-repo regression tests for ``_filtered_targets``, the shared
predicate-plus-on-disk-verification helper every scoped gate (markdown,
workflow YAML, YAML style) calls after :func:`_changed_paths_since_base`.

Covers the item-2 fix (round 2 review, perf/git-hook-latency): a path git
reports as changed (Added, Copied, Modified, or Renamed --
``--diff-filter=ACMR`` already excludes Deleted) but that is absent from the
worktree must fail the gate loudly, not be silently dropped (the previous
behavior) and not trigger a full-repo fallback that cannot see the
staged/committed blob responsible for the report.

Each gate's own test file (``test_workflow_checks.py``,
``test_yaml_style_checks.py``) keeps one thin ``test_missing_from_disk_raises``
proving its predicate reaches this shared path; the real-repo mechanics of
WHY a reported path can be missing are proven once, here.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

import pytest

_SCRIPTS_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_SCRIPTS_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_VALIDATION_DIR))

from checks_changed_paths import ChangedPathMissingError, _filtered_targets  # noqa: E402

pytestmark = pytest.mark.usefixtures("no_gh")

GitCmd = Callable[..., CompletedProcess[str]]
RepoFactory = Callable[[Path], Path]


def _is_readme(path: str) -> bool:
    return path == "README.md"


def _is_new_file(path: str) -> bool:
    return path == "new_file.md"


def _is_doomed(path: str) -> bool:
    return path == "doomed.md"


class TestMissingFromDiskFailsLoudly:
    """Positive case: a path git still reports as changed, but that is
    genuinely gone from the worktree, must raise."""

    def test_dirty_deletion_after_staged_modification_raises(
        self, tmp_path: Path, make_repo_with_base: RepoFactory, git_cmd: GitCmd
    ) -> None:
        """Stage a modification (index differs from HEAD: ``git diff
        --cached HEAD`` reports Modified), then delete the file from the
        worktree WITHOUT staging that deletion (a "dirty deletion"). The
        unstaged source (``git diff``, index vs worktree) correctly reports
        this as Deleted and is excluded there by ACMR -- but the staged
        source already put the path into the union, and the file really is
        gone from disk.

        Verified this session (git 2.43, real subprocess calls via
        ``make_repo_with_base``): ``git diff --cached HEAD`` keeps
        reporting the path as Modified after an out-of-band ``rm``, while
        ``git diff`` (unstaged) reports it Deleted, excluded by
        ``--diff-filter=ACMR``.
        """
        repo = make_repo_with_base(tmp_path)
        (repo / "README.md").write_text("seed\nstaged change\n", encoding="utf-8")
        git_cmd(repo, "add", "README.md")
        (repo / "README.md").unlink()

        with pytest.raises(ChangedPathMissingError, match="README.md"):
            _filtered_targets(repo, "Test", _is_readme)

    def test_error_message_names_the_gate_and_the_path(
        self, tmp_path: Path, make_repo_with_base: RepoFactory, git_cmd: GitCmd
    ) -> None:
        """The failure must be actionable: which gate, which path."""
        repo = make_repo_with_base(tmp_path)
        (repo / "README.md").write_text("seed\nstaged change\n", encoding="utf-8")
        git_cmd(repo, "add", "README.md")
        (repo / "README.md").unlink()

        with pytest.raises(ChangedPathMissingError) as exc_info:
            _filtered_targets(repo, "Markdown lint", _is_readme)

        message = str(exc_info.value)
        assert "Markdown lint" in message
        assert "README.md" in message


class TestStagedThenRestoredDoesNotMisfire:
    """Inverse guard (mirror obligation): a path that was staged and then
    fully, cleanly restored must not be reported as changed at all, so the
    new loud-failure path must never even see it."""

    def test_staged_then_fully_restored_reports_no_change(
        self, tmp_path: Path, make_repo_with_base: RepoFactory, git_cmd: GitCmd
    ) -> None:
        """Stage a modification, then restore BOTH the index and the
        worktree back to HEAD (``git restore --staged --worktree``, the
        standard way to undo a stage). Nothing is different from HEAD
        anymore, so nothing should be reported as changed, and the
        dirty-deletion failure path introduced above must not misfire on
        a path that only APPEARED in an intermediate state.
        """
        repo = make_repo_with_base(tmp_path)
        (repo / "README.md").write_text("seed\nstaged change\n", encoding="utf-8")
        git_cmd(repo, "add", "README.md")
        git_cmd(repo, "restore", "--staged", "--worktree", "README.md")

        assert _filtered_targets(repo, "Test", _is_readme) == []

    def test_staged_deletion_restored_to_worktree_is_included_and_present(
        self, tmp_path: Path, make_repo_with_base: RepoFactory, git_cmd: GitCmd
    ) -> None:
        """A different restore shape: stage a deletion (``git rm``, which
        removes the file from both the index and the worktree), then
        restore ONLY the worktree copy from HEAD while leaving the
        deletion staged (``git checkout HEAD -- <path>`` in older git
        restores both; this uses ``git restore --source=HEAD --worktree``
        to touch only the worktree, per git-restore(1)). The file is once
        again present on disk, so no ``ChangedPathMissingError`` is
        possible even though the index still disagrees with HEAD.
        """
        repo = make_repo_with_base(tmp_path)
        git_cmd(repo, "rm", "-q", "README.md")
        git_cmd(repo, "restore", "--source=HEAD", "--worktree", "README.md")

        result = _filtered_targets(repo, "Test", _is_readme)

        assert result == ["README.md"]
        assert (repo / "README.md").is_file()


class TestNonMatchingMissingPathsDoNotRaise:
    """The predicate gates which paths are even checked for presence: a
    missing path that the predicate rejects must not raise (only paths the
    gate actually cares about are worth failing loudly over)."""

    def test_missing_path_that_predicate_rejects_is_silently_excluded(
        self, tmp_path: Path, make_repo_with_base: RepoFactory, git_cmd: GitCmd
    ) -> None:
        repo = make_repo_with_base(tmp_path)
        (repo / "notes.txt").write_text("staged\n", encoding="utf-8")
        git_cmd(repo, "add", "notes.txt")
        (repo / "notes.txt").unlink()

        # Predicate only accepts README.md; notes.txt's dirty deletion is
        # invisible to this call because the predicate never matches it.
        result = _filtered_targets(repo, "Test", _is_readme)

        assert result == []


class TestBranchAddedFileMissingFromDisk:
    """Review finding (perf/git-hook-latency, round 3): the OLD docstring
    and error message claimed a reported-but-missing path "can only happen
    via a dirty deletion" (unstaged ``rm`` after a staged add/modify). That
    claim is false for a file a BRANCH COMMIT adds: ``base...HEAD`` reports
    it because it is part of HEAD's committed history -- the exact content
    a push will send -- regardless of what the index or worktree do
    afterwards. A staged-but-uncommitted deletion (``git rm``) does not
    remove the file from HEAD, so this must still fail closed, and the
    guidance must not merely say "stage the deletion": staging it is
    already what happened in that scenario, and it does not fix anything,
    because HEAD (not the index) is what a push actually sends.
    """

    def test_staged_deletion_of_a_branch_added_file_fails_closed(
        self, tmp_path: Path, make_repo_with_base: RepoFactory, git_cmd: GitCmd
    ) -> None:
        """Commit ``new_file.md`` on the branch (so ``base...HEAD`` reports
        it Added: it is genuinely part of what HEAD will push), then stage
        its removal with ``git rm`` WITHOUT committing that removal. HEAD
        still contains the file; the index and worktree do not. The gate
        must fail closed instead of silently validating a subset of the
        commit that is about to be pushed, and the message must name the
        staged deletion without suggesting staging as the fix.
        """
        repo = make_repo_with_base(tmp_path)
        (repo / "new_file.md").write_text("added on branch\n", encoding="utf-8")
        git_cmd(repo, "add", "new_file.md")
        git_cmd(repo, "commit", "-q", "-m", "feat: add new_file")
        git_cmd(repo, "rm", "-q", "new_file.md")

        with pytest.raises(ChangedPathMissingError) as exc_info:
            _filtered_targets(repo, "Test", _is_new_file)

        message = str(exc_info.value)
        assert "new_file.md" in message
        assert "staged deletion" in message
        assert "Commit the deletion, restore the file, or clean/stash" in message
        assert "Stage the deletion" not in message

    def test_dirty_deletion_of_a_branch_added_file_fails_closed(
        self, tmp_path: Path, make_repo_with_base: RepoFactory, git_cmd: GitCmd
    ) -> None:
        """Same branch-added file, but the removal is a bare ``rm`` (a
        dirty deletion): the index still holds the blob, only the worktree
        copy is gone. ``base...HEAD`` still reports it Added, so this must
        also fail closed; the diagnostic staged-deletion check must not
        misclassify it since the index was never touched.
        """
        repo = make_repo_with_base(tmp_path)
        (repo / "new_file.md").write_text("added on branch\n", encoding="utf-8")
        git_cmd(repo, "add", "new_file.md")
        git_cmd(repo, "commit", "-q", "-m", "feat: add new_file")
        (repo / "new_file.md").unlink()

        with pytest.raises(ChangedPathMissingError) as exc_info:
            _filtered_targets(repo, "Test", _is_new_file)

        message = str(exc_info.value)
        assert "new_file.md (reason unknown)" in message
        assert "Commit the deletion, restore the file, or clean/stash" in message


class TestCommittedDeletionIsExcludedNotAFailure:
    """Mirror obligation for the two fixtures above: a deletion that IS
    committed is genuinely absent from both HEAD and the worktree -- there
    is nothing left to push and nothing for the gate to inspect.
    ``--diff-filter=ACMR`` must exclude it from the union entirely, so it
    must never reach the missing-from-disk check, let alone raise.
    """

    def test_committed_deletion_is_not_reported_and_does_not_raise(
        self, tmp_path: Path, make_repo_with_base: RepoFactory, git_cmd: GitCmd
    ) -> None:
        """Add ``doomed.md`` and push it to ``origin/main`` so it becomes
        part of the BASE the branch is later compared against, then delete
        it in a committed follow-up. Relative to base, this is a genuine
        Deleted (``D``) entry, excluded by ACMR -- never a
        reported-but-missing path.
        """
        repo = make_repo_with_base(tmp_path)
        (repo / "doomed.md").write_text("temporary\n", encoding="utf-8")
        git_cmd(repo, "add", "doomed.md")
        git_cmd(repo, "commit", "-q", "-m", "feat: add doomed")
        git_cmd(repo, "push", "-q", "origin", "main")
        git_cmd(repo, "rm", "-q", "doomed.md")
        git_cmd(repo, "commit", "-q", "-m", "chore: remove doomed")

        result = _filtered_targets(repo, "Test", _is_doomed)

        assert result == []
