"""Regression tests for manual semgrep scan file selection scope."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import scripts.security.run_semgrep as run_semgrep
from scripts.security.run_semgrep import ScanScopeError, SemgrepScanner


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _repo_with_initial_commit(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.invalid")
    (repo / "sample.py").write_text("print('before')\n", encoding="utf-8")
    _git(repo, "add", "sample.py")
    _git(repo, "commit", "-q", "-m", "initial")
    return repo


def _scanner(repo: Path) -> SemgrepScanner:
    with patch.object(SemgrepScanner, "_find_repo_root", return_value=repo):
        return SemgrepScanner()


def _branch_with_committed_change(repo: Path, filename: str = "sample.py") -> None:
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / filename).write_text("print('after committed edit')\n", encoding="utf-8")
    _git(repo, "add", filename)
    _git(repo, "commit", "-q", "-m", "committed change")


class TestChangedFileSelectionScope:
    """The manual scanner selects committed branch changes, not working-tree edits."""

    def test_uncommitted_edits_are_not_selected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _repo_with_initial_commit(tmp_path)
        _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")

        (repo / "sample.py").write_text("print('after uncommitted edit')\n", encoding="utf-8")
        monkeypatch.chdir(repo)

        assert _scanner(repo)._get_changed_files() == []

    def test_nonascii_committed_path_is_selected_when_git_quotes_paths(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _repo_with_initial_commit(tmp_path)
        _branch_with_committed_change(repo, "café.py")
        _git(repo, "config", "core.quotePath", "true")
        monkeypatch.chdir(repo)

        assert _scanner(repo)._get_changed_files() == [repo / "café.py"]

    @pytest.mark.parametrize("stage_edit", [False, True], ids=["unstaged", "staged"])
    def test_uncommitted_edit_to_selected_file_blocks_scan(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        stage_edit: bool,
    ) -> None:
        repo = _repo_with_initial_commit(tmp_path)
        _branch_with_committed_change(repo)
        (repo / "sample.py").write_text("print('dirty edit')\n", encoding="utf-8")
        if stage_edit:
            _git(repo, "add", "sample.py")
        monkeypatch.chdir(repo)

        with pytest.raises(
            ScanScopeError,
            match="uncommitted changes affect selected scan files",
        ):
            _scanner(repo)._get_changed_files()

    def test_committed_deletion_is_not_selected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _repo_with_initial_commit(tmp_path)
        _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        _git(repo, "checkout", "-q", "-b", "feature")
        (repo / "sample.py").unlink()
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "delete sample")
        monkeypatch.chdir(repo)

        assert _scanner(repo)._get_changed_files() == []

    def test_tracked_file_fallback_without_merge_base(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _repo_with_initial_commit(tmp_path)
        monkeypatch.chdir(repo)

        scanner = _scanner(repo)

        assert scanner._get_changed_files() == [repo / "sample.py"]
        assert "git ls-files" in scanner.scan_scope
        assert "working tree" in scanner.scan_scope

    def test_git_merge_base_oserror_raises(self, tmp_path: Path) -> None:
        scanner = _scanner(tmp_path)

        with (
            patch(
                "scripts.security.run_semgrep.subprocess.run",
                side_effect=OSError("git executable missing"),
            ),
            pytest.raises(ScanScopeError, match="git merge-base failed"),
        ):
            scanner._get_changed_files()

    def test_git_file_enumeration_error_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _repo_with_initial_commit(tmp_path)
        bad_index = tmp_path / "bad-index"
        bad_index.write_bytes(b"not-a-git-index")
        monkeypatch.setenv("GIT_INDEX_FILE", str(bad_index))
        monkeypatch.chdir(repo)

        with pytest.raises(ScanScopeError, match="git ls-files"):
            _scanner(repo)._get_changed_files()

    def test_git_file_enumeration_error_makes_run_exit_1(self, tmp_path: Path) -> None:
        scanner = _scanner(tmp_path)

        with (
            patch.object(scanner, "_check_semgrep_installed", return_value=True),
            patch.object(
                scanner,
                "_get_changed_files",
                side_effect=ScanScopeError("git ls-files failed"),
            ),
        ):
            assert scanner.run() == 1

    def test_zero_target_result_discloses_scope(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        repo = _repo_with_initial_commit(tmp_path)
        _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        monkeypatch.chdir(repo)
        scanner = _scanner(repo)
        caplog.set_level(logging.INFO)

        with patch.object(scanner, "_check_semgrep_installed", return_value=True):
            assert scanner.run() == 0

        assert "PASS: No files to scan" in caplog.text
        assert "merge base" in caplog.text
        assert "untracked" in caplog.text
        assert "uncommitted" in caplog.text

    def test_cli_help_discloses_file_selection(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["run_semgrep.py", "--help"])

        with pytest.raises(SystemExit) as exc_info:
            run_semgrep.main()

        assert exc_info.value.code == 0
        help_text = capsys.readouterr().out
        assert "merge base" in help_text
        assert "git ls-files" in help_text
        assert "working-tree contents" in help_text
        assert "uncommitted" in help_text

    def test_module_docstring_discloses_committed_diff_scope(self) -> None:
        flat_doc = " ".join((run_semgrep.__doc__ or "").split())
        lower_doc = flat_doc.lower()

        assert "merge base with origin/main" in lower_doc
        assert "git ls-files" in lower_doc
        assert "working-tree contents" in lower_doc
        assert "uncommitted" in lower_doc
        assert "untracked" in lower_doc
        assert "PASS: No files to scan" in flat_doc
