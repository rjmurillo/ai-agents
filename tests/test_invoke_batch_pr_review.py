"""Tests for invoke_batch_pr_review.py worktree management."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts import invoke_batch_pr_review
from scripts.invoke_batch_pr_review import (
    MAX_AUDITED_DIRTY_ENTRIES,
    SUBPROCESS_TIMEOUT_SECONDS,
    WorktreeStatus,
    get_pr_branch,
    get_worktree_status,
    main,
    main_worktree_of,
    print_status_table,
    push_worktree_changes,
    remove_worktree,
    run_gh,
    run_git,
)
from scripts.maintenance import removal_audit


class TestGetPrBranch:
    @patch("scripts.invoke_batch_pr_review.subprocess.run")
    def test_run_wrappers_pass_timeout(self, mock_run: MagicMock) -> None:
        run_git("status")
        run_gh("pr", "list")

        assert mock_run.call_count == 2
        assert all(
            call.kwargs["timeout"] == SUBPROCESS_TIMEOUT_SECONDS for call in mock_run.call_args_list
        )

    @patch("scripts.invoke_batch_pr_review.run_gh")
    def test_returns_branch_name(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = MagicMock(returncode=0, stdout='{"headRefName": "feat/my-branch"}')
        assert get_pr_branch(123) == "feat/my-branch"

    @patch("scripts.invoke_batch_pr_review.run_gh")
    def test_returns_none_on_failure(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = MagicMock(returncode=1, stdout="")
        assert get_pr_branch(999) is None

    @patch("scripts.invoke_batch_pr_review.run_gh")
    def test_returns_none_on_bad_json(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = MagicMock(returncode=0, stdout="not-json")
        assert get_pr_branch(123) is None


class TestWorktreeStatus:
    def test_dataclass_defaults(self) -> None:
        status = WorktreeStatus(pr=1, path=Path("/tmp/wt"), exists=False)
        assert status.clean is None
        assert status.branch is None
        assert status.commit is None
        assert status.unpushed is None


class TestGetWorktreeStatus:
    @patch("scripts.invoke_batch_pr_review.run_git")
    def test_nonexistent_path_returns_exists_false(self, mock_git: MagicMock) -> None:
        status = get_worktree_status(42, Path("/nonexistent"))
        assert status.exists is False
        assert status.pr == 42


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a git command, isolated from the caller's locale.

    Signature and body are identical to
    ``tests/test_pr_autofix_worktree_identity.py::_git`` (verified this
    session by reading that file), the closest existing analog: both files
    build throwaway git repos to exercise
    ``scripts.github_core.worktree_identity``. No divergence.
    """
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=check,
    )


def _prepare_pushable_worktree(root: Path) -> Path:
    """Create a pushable worktree with bot identity and an upstream remote."""
    origin = root / "origin.git"
    worktree = root / "worktree-pr-1"

    _git(["init", "--bare", "--initial-branch=main", str(origin)], root)
    _git(["clone", str(origin), str(worktree)], root)
    _git(["config", "user.name", "rjmurillo-bot"], worktree)
    _git(["config", "user.email", "rjmurillo-bot@users.noreply.github.com"], worktree)
    (worktree / "README.md").write_text("base\n")
    _git(["add", "README.md"], worktree)
    _git(["commit", "-m", "base"], worktree)
    _git(["push", "origin", "main"], worktree)
    return worktree


class TestPrintStatusTable:
    def test_prints_without_error(self) -> None:
        statuses = [
            WorktreeStatus(pr=1, path=Path("/wt"), exists=True, clean=True, branch="main"),
        ]
        print_status_table(statuses)


class TestMain:
    @patch("scripts.invoke_batch_pr_review.run_git")
    def test_status_operation(self, mock_git: MagicMock) -> None:
        mock_git.return_value = MagicMock(returncode=0, stdout="/fake/repo\n")
        result = main(
            [
                "--pr-numbers",
                "1",
                "2",
                "--operation",
                "status",
                "--worktree-root",
                "/tmp",
            ]
        )
        assert result == 0

    @patch("scripts.invoke_batch_pr_review.get_worktree_status")
    def test_returns_3_on_subprocess_timeout(self, mock_status: MagicMock) -> None:
        mock_status.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=60)
        result = main(
            [
                "--pr-numbers",
                "1",
                "--operation",
                "status",
                "--worktree-root",
                "/tmp",
            ]
        )
        assert result == 3


class TestPushWorktreeChanges:
    def test_repins_leaked_identity_before_cleanup_commit(self, tmp_path: Path) -> None:
        """A leaked Test <test@test.com> identity must not reach the cleanup commit."""
        worktree = _prepare_pushable_worktree(tmp_path)

        _git(["config", "user.name", "Test"], worktree)
        _git(["config", "user.email", "test@test.com"], worktree)
        (worktree / "README.md").write_text("base\nchange\n")

        assert push_worktree_changes(1, tmp_path) is True

        author = _git(["log", "-1", "--format=%an <%ae>"], worktree).stdout.strip()
        assert author == "rjmurillo-bot <rjmurillo-bot@users.noreply.github.com>"
        local_email = _git(["config", "--local", "user.email"], worktree).stdout.strip()
        assert local_email == "rjmurillo-bot@users.noreply.github.com"

    def test_clean_and_pushed_worktree_skips_identity_reset(self, tmp_path: Path) -> None:
        """A clean, already-pushed worktree must not need a reset or commit."""
        _prepare_pushable_worktree(tmp_path)

        from scripts import invoke_batch_pr_review

        with patch.object(invoke_batch_pr_review, "reset_worktree_identity") as mock_reset:
            result = push_worktree_changes(1, tmp_path)

        assert result is True
        mock_reset.assert_not_called()

    def test_operator_identity_is_forwarded_to_reset(self, tmp_path: Path) -> None:
        """The CLI must forward human operator mode through the cleanup path."""
        from scripts import invoke_batch_pr_review

        status = WorktreeStatus(
            pr=1,
            path=tmp_path / "worktree-pr-1",
            exists=True,
            clean=False,
            branch="main",
            commit=None,
            unpushed=True,
        )
        with (
            patch.object(invoke_batch_pr_review, "get_worktree_status", return_value=status),
            patch.object(invoke_batch_pr_review, "reset_worktree_identity") as mock_reset,
            patch.object(invoke_batch_pr_review, "run_git") as mock_run_git,
            patch.object(invoke_batch_pr_review, "remove_worktree", return_value=True),
        ):
            mock_run_git.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = main(
                [
                    "--pr-numbers",
                    "1",
                    "--operation",
                    "cleanup",
                    "--worktree-root",
                    str(tmp_path),
                    "--operator-identity",
                    "rjmurillo",
                ]
            )

        assert result == 0
        mock_reset.assert_called_once_with(status.path, operator="rjmurillo")


def _audit_records() -> list[dict]:
    """Read the shared audit log the conftest fixture redirects tests to."""
    log_path = removal_audit.audit_log_path_for("unused")
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def linked_worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A main repo with one linked worktree named ``worktree-pr-7``.

    Returns ``(worktree_root, worktree_path)``. The cwd is the main repo, as
    in real use, because ``remove_worktree`` runs ``git worktree remove`` there.
    """
    main_repo = tmp_path / "main"
    main_repo.mkdir()
    _git(["init", "--initial-branch=main"], main_repo)
    _git(["config", "user.name", "rjmurillo-bot"], main_repo)
    _git(["config", "user.email", "rjmurillo-bot@users.noreply.github.com"], main_repo)
    (main_repo / "README.md").write_text("base\n")
    _git(["add", "README.md"], main_repo)
    _git(["commit", "-m", "base"], main_repo)
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree = worktree_root / "worktree-pr-7"
    _git(["worktree", "add", "-b", "feat/seven", str(worktree)], main_repo)
    monkeypatch.chdir(main_repo)
    return worktree_root, worktree


class TestRemoveWorktreeAudit:
    def test_clean_removal_appends_one_record(self, linked_worktree: tuple[Path, Path]) -> None:
        root, worktree = linked_worktree

        assert remove_worktree(7, root) is True

        assert not worktree.exists()
        [record] = _audit_records()
        assert record["tool"] == "invoke_batch_pr_review"
        assert record["path"] == str(worktree)
        assert record["pr"] == 7
        assert record["branch"] == "feat/seven"
        assert record["force"] is False
        assert record["clean"] is True
        assert record["dirtyEntryCount"] == 0
        assert record["dirtyEntries"] == []

    def test_forced_removal_names_the_untracked_file_it_deleted(
        self, linked_worktree: tuple[Path, Path]
    ) -> None:
        root, worktree = linked_worktree
        (worktree / "report.json").write_text("operator artifact\n")

        assert remove_worktree(7, root, force=True) is True

        assert not worktree.exists()
        [record] = _audit_records()
        assert record["force"] is True
        assert record["clean"] is False
        assert record["dirtyEntries"] == ["?? report.json"]
        assert record["dirtyEntryCount"] == 1

    def test_dirty_entries_are_capped_but_the_count_is_exact(
        self, linked_worktree: tuple[Path, Path]
    ) -> None:
        root, worktree = linked_worktree
        total = MAX_AUDITED_DIRTY_ENTRIES + 5
        for index in range(total):
            (worktree / f"scratch-{index:03d}.txt").write_text("x\n")

        assert remove_worktree(7, root, force=True) is True

        [record] = _audit_records()
        assert record["dirtyEntryCount"] == total
        assert len(record["dirtyEntries"]) == MAX_AUDITED_DIRTY_ENTRIES

    def test_refused_removal_writes_no_record(self, linked_worktree: tuple[Path, Path]) -> None:
        root, worktree = linked_worktree
        (worktree / "report.json").write_text("operator artifact\n")

        assert remove_worktree(7, root) is False

        assert (worktree / "report.json").exists()
        assert _audit_records() == []

    def test_missing_worktree_writes_no_record(self, tmp_path: Path) -> None:
        assert remove_worktree(99, tmp_path) is True

        assert _audit_records() == []

    def test_failed_git_removal_writes_no_record(
        self, linked_worktree: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        root, worktree = linked_worktree
        real_run_git = invoke_batch_pr_review.run_git

        def fail_remove(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[:2] == ("worktree", "remove"):
                return subprocess.CompletedProcess(args, 1, "", "boom")
            return real_run_git(*args, **kwargs)

        with patch.object(invoke_batch_pr_review, "run_git", side_effect=fail_remove):
            assert remove_worktree(7, root) is False

        assert worktree.exists()
        assert _audit_records() == []
        assert "Failed to remove" in capsys.readouterr().out

    def test_unlocatable_main_worktree_blocks_removal(
        self, linked_worktree: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        root, worktree = linked_worktree

        with patch.object(invoke_batch_pr_review, "main_worktree_of", return_value=None):
            assert remove_worktree(7, root, force=True) is False

        assert worktree.exists()
        assert _audit_records() == []
        assert "cannot be audited" in capsys.readouterr().out

    def test_unwritable_log_warns_but_still_reports_the_removal(
        self, linked_worktree: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        root, worktree = linked_worktree

        with patch.object(removal_audit, "append_record", side_effect=OSError("disk full")):
            assert remove_worktree(7, root) is True

        assert not worktree.exists()
        captured = capsys.readouterr()
        assert "audit record was not written" in captured.err
        assert "disk full" in captured.err


class TestMainWorktreeOf:
    def test_returns_the_main_checkout_from_a_linked_worktree(
        self, linked_worktree: tuple[Path, Path]
    ) -> None:
        _, worktree = linked_worktree

        resolved = main_worktree_of(worktree)

        assert resolved is not None
        assert Path(resolved).name == "main"

    @patch("scripts.invoke_batch_pr_review.run_git")
    def test_returns_none_when_git_fails(self, mock_git: MagicMock) -> None:
        mock_git.return_value = MagicMock(returncode=128, stdout="")

        assert main_worktree_of(Path("/wt")) is None

    @patch("scripts.invoke_batch_pr_review.run_git")
    def test_returns_none_on_empty_output(self, mock_git: MagicMock) -> None:
        mock_git.return_value = MagicMock(returncode=0, stdout="")

        assert main_worktree_of(Path("/wt")) is None

    @patch("scripts.invoke_batch_pr_review.run_git")
    def test_returns_none_on_unexpected_first_line(self, mock_git: MagicMock) -> None:
        mock_git.return_value = MagicMock(returncode=0, stdout="HEAD abc\n")

        assert main_worktree_of(Path("/wt")) is None
