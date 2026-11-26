"""Git repository fixtures shared by the scanners' ``--diff-scope`` tests."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest


def run_git(repo: Path, *args: str) -> None:
    """Run a git command in the given repo, failing loudly on error."""
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def make_repo_with_diff(repo: Path, governance_doc: str | None = None) -> None:
    """Create a repo whose feature branch adds one file against main.

    ``governance_doc`` names a file committed on main, for a repository that
    adopted the golden principles. ``None`` builds a consumer repository.
    """
    run_git(repo, "init", "-b", "main")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test")
    (repo / "base.py").write_text("x = 1\n", encoding="utf-8")
    run_git(repo, "add", "base.py")
    if governance_doc is not None:
        doc = repo / governance_doc
        doc.parent.mkdir(parents=True)
        doc.write_text("# Golden principles\n", encoding="utf-8")
        run_git(repo, "add", governance_doc)
    run_git(repo, "commit", "-m", "base")
    run_git(repo, "checkout", "-b", "feature")
    (repo / "changed.py").write_text("y = 2\n", encoding="utf-8")
    run_git(repo, "add", "changed.py")
    run_git(repo, "commit", "-m", "change")


class DiffFileSelectionContract:
    """``get_diff_files`` behavior every diff-scoped scanner must keep.

    A subclass named ``Test*`` sets ``get_diff_files`` and ``governance_doc``.
    """

    get_diff_files: Callable[[str], list[str]]
    governance_doc: str | None = None

    def test_returns_only_changed_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_repo_with_diff(tmp_path, self.governance_doc)
        monkeypatch.chdir(tmp_path)
        result = type(self).get_diff_files("main")
        # Paths are anchored to the git root so they resolve from any cwd.
        assert len(result) == 1
        assert os.path.isabs(result[0])
        assert result[0].endswith("/changed.py")
        assert os.path.isfile(result[0])

    def test_returns_empty_when_no_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_repo_with_diff(tmp_path, self.governance_doc)
        run_git(tmp_path, "checkout", "main")
        monkeypatch.chdir(tmp_path)
        assert type(self).get_diff_files("main") == []
