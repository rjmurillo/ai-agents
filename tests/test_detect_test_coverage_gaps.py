"""Tests for detect_test_coverage_gaps.py PowerShell test coverage detection."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.detect_test_coverage_gaps import (
    find_test_file,
    load_ignore_patterns,
    should_ignore,
)


class TestShouldIgnore:
    def test_ignores_test_files(self) -> None:
        patterns = [r"\.Tests\.ps1$"]
        assert should_ignore("scripts/Foo.Tests.ps1", patterns) is True

    def test_does_not_ignore_regular_files(self) -> None:
        patterns = [r"\.Tests\.ps1$"]
        assert should_ignore("scripts/Foo.ps1", patterns) is False

    def test_ignores_build_directory(self) -> None:
        patterns = [r"build[/\\]"]
        assert should_ignore("build/output.ps1", patterns) is True

    def test_empty_patterns_ignores_nothing(self) -> None:
        assert should_ignore("any/file.ps1", []) is False


class TestLoadIgnorePatterns:
    def test_loads_patterns_from_file(self, tmp_path: Path) -> None:
        ignore = tmp_path / "ignore.txt"
        ignore.write_text("pattern1\n# comment\npattern2\n\n", encoding="utf-8")
        patterns = load_ignore_patterns(str(ignore))
        assert patterns == ["pattern1", "pattern2"]

    def test_returns_empty_for_missing_file(self) -> None:
        assert load_ignore_patterns("/nonexistent/file") == []


class TestFindTestFile:
    def test_finds_test_in_same_directory(self, tmp_path: Path) -> None:
        (tmp_path / "Foo.ps1").write_text("", encoding="utf-8")
        (tmp_path / "Foo.Tests.ps1").write_text("", encoding="utf-8")
        assert find_test_file("Foo.ps1", tmp_path) is True

    def test_finds_test_in_tests_subdirectory(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        (tmp_path / "Foo.ps1").write_text("", encoding="utf-8")
        (tmp_path / "tests" / "Foo.Tests.ps1").write_text("", encoding="utf-8")
        assert find_test_file("Foo.ps1", tmp_path) is True

    def test_returns_false_when_no_test(self, tmp_path: Path) -> None:
        (tmp_path / "Foo.ps1").write_text("", encoding="utf-8")
        assert find_test_file("Foo.ps1", tmp_path) is False


class TestTheDetectorRunsWithoutAnEditableInstall:
    """It is launched as a subprocess by new_pr.py, not imported.

    Running ``python <repo>/scripts/detect_test_coverage_gaps.py`` puts
    ``<repo>/scripts`` on ``sys.path``, not ``<repo>``, so the
    ``scripts.github_core.repo`` import resolves only where the project is
    installed. A linked worktree with its own venv, or a plain ``python3``,
    has neither, and the crash was swallowed by the caller (issue #3391).
    """

    _SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "detect_test_coverage_gaps.py"

    @staticmethod
    def _clean_env() -> dict[str, str]:
        """Environment with nothing that could supply the import path."""
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        env["PYTHONNOUSERSITE"] = "1"
        return env

    @staticmethod
    def _argv(script: Path) -> list[str]:
        """Launch with site processing off, which is what makes this a guard.

        The test venv installs this project editable, so a plain subprocess
        imports ``scripts`` through a .pth file no matter what the script
        does, and the guard would pass with the fix reverted. ``-S`` skips
        site processing so the .pth is not read, and ``-I`` drops the
        environment and the user site directory. The script's own path insert
        is then the only thing that can satisfy the import, which is the
        condition the reported worktree was in.
        """
        return [sys.executable, "-S", "-I", str(script), "--staged-only"]

    def _run(self, cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self._argv(self._SCRIPT),
            cwd=str(cwd),
            env=self._clean_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

    def test_it_imports_without_the_editable_install(self) -> None:
        result = self._run(self._SCRIPT.parents[1])
        assert "ModuleNotFoundError" not in result.stderr, result.stderr
        assert result.returncode == 0, result.stderr

    def test_it_imports_from_a_linked_worktree(self, tmp_path: Path) -> None:
        """The reported repro: a linked worktree has no editable install."""
        repo = self._SCRIPT.parents[1]
        worktree = tmp_path / "wt"
        add = subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if add.returncode != 0:
            pytest.skip(f"git worktree add unavailable: {add.stderr}")
        try:
            script = worktree / "scripts" / "detect_test_coverage_gaps.py"
            # The worktree is checked out at HEAD, so it carries the committed
            # detector. Copy in the working-tree one so the guard tests the
            # code under review rather than the last commit.
            script.write_text(self._SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            result = subprocess.run(
                self._argv(script),
                cwd=str(worktree),
                env=self._clean_env(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            assert "ModuleNotFoundError" not in result.stderr, result.stderr
            assert result.returncode == 0, result.stderr
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=str(repo),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
