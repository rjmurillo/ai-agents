#!/usr/bin/env python3
"""Tests for the --diff-scope flag in scan_principles."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/golden-principles/scripts/scan_principles.py")
get_diff_files = mod.get_diff_files
main = mod.main
EXIT_SUCCESS = mod.EXIT_SUCCESS
EXIT_VIOLATIONS = mod.EXIT_VIOLATIONS


def _run_git(repo: Path, *args: str) -> None:
    """Run a git command in the given repo, failing loudly on error."""
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
    )


def _make_repo_with_diff(repo: Path) -> None:
    """Create a git repo on a feature branch with one file changed vs main."""
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test")
    (repo / "base.py").write_text("x = 1\n")
    _run_git(repo, "add", "base.py")
    _run_git(repo, "commit", "-m", "base")
    _run_git(repo, "checkout", "-b", "feature")
    (repo / "changed.py").write_text("y = 2\n")
    _run_git(repo, "add", "changed.py")
    _run_git(repo, "commit", "-m", "change")


class TestGetDiffFiles:
    """Tests for diff-scoped file selection (--diff-scope)."""

    def test_returns_only_changed_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = get_diff_files("main")
        assert result == ["changed.py"]

    def test_returns_empty_when_no_changes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_repo_with_diff(tmp_path)
        _run_git(tmp_path, "checkout", "main")
        monkeypatch.chdir(tmp_path)
        result = get_diff_files("main")
        assert result == []

    def test_returns_empty_when_git_missing(self) -> None:
        with patch.object(mod.subprocess, "run", side_effect=FileNotFoundError):
            result = get_diff_files("main")
        assert result == []

    def test_returns_empty_on_unknown_base(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = get_diff_files("does-not-exist")
        assert result == []

    def test_drops_traversal_paths(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="changed.py\n../escape.py\nfoo/../bar.py\n",
        )
        with patch.object(mod.subprocess, "run", return_value=completed):
            result = get_diff_files("main")
        assert result == ["changed.py"]


class TestMainDiffScope:
    """Tests for the --diff-scope main entry path."""

    def test_diff_scope_scans_only_changed_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_repo_with_diff(tmp_path)
        # A pre-existing shell script on the base would trip GP-001 on a
        # whole-tree scan, but it is not in the diff so --diff-scope ignores it.
        (tmp_path / "legacy.sh").write_text("echo hi\n")
        _run_git(tmp_path, "checkout", "main")
        _run_git(tmp_path, "add", "legacy.sh")
        _run_git(tmp_path, "commit", "-m", "legacy shell on main")
        _run_git(tmp_path, "checkout", "feature")
        _run_git(tmp_path, "rebase", "main")
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["scan_principles.py", "--diff-scope", "main"]):
            result = main()
        assert result == EXIT_SUCCESS

    def test_diff_scope_flags_violation_in_changed_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_repo_with_diff(tmp_path)
        # Add a new shell script in the diff: GP-001 (script-language) is an error.
        (tmp_path / "added.sh").write_text("echo added\n")
        _run_git(tmp_path, "add", "added.sh")
        _run_git(tmp_path, "commit", "-m", "add shell script")
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["scan_principles.py", "--diff-scope", "main"]):
            result = main()
        assert result == EXIT_VIOLATIONS
