"""Regression tests for manual semgrep scan file selection scope."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

import scripts.security.run_semgrep as run_semgrep
from scripts.security.run_semgrep import SemgrepScanner


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


class TestChangedFileSelectionScope:
    """The manual scanner selects committed branch changes, not working-tree edits."""

    def test_uncommitted_edits_are_not_selected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.name", "Test")
        _git(repo, "config", "user.email", "test@example.invalid")
        (repo / "sample.py").write_text("print('before')\n", encoding="utf-8")
        _git(repo, "add", "sample.py")
        _git(repo, "commit", "-q", "-m", "initial")
        _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")

        (repo / "sample.py").write_text("print('after uncommitted edit')\n", encoding="utf-8")
        monkeypatch.chdir(repo)

        with patch.object(SemgrepScanner, "_find_repo_root", return_value=repo):
            scanner = SemgrepScanner()

        assert scanner._get_changed_files() == []

    def test_module_docstring_discloses_committed_diff_scope(self) -> None:
        flat_doc = " ".join((run_semgrep.__doc__ or "").split())
        lower_doc = flat_doc.lower()

        assert "merge base with origin/main" in lower_doc
        assert "uncommitted" in lower_doc
        assert "untracked" in lower_doc
        assert "PASS: No files to scan" in flat_doc
