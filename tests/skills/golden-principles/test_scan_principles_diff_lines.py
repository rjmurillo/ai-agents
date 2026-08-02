"""Tests for diff-scoped line-number filtering added to scan_principles.

Verifies that --diff-scope mode suppresses pre-existing violations on
unchanged lines while still reporting violations introduced on changed lines.
"""

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

_SCRIPTS_DIR = str(
    Path(__file__).resolve().parents[3]
    / ".claude/skills/golden-principles/scripts"
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import scan_principles_core as core
from scan_principles_core import (
    _parse_hunk_header,
    _run_git_diff,
    get_diff_line_numbers,
)

scan_mod = import_skill_script(".claude/skills/golden-principles/scripts/scan_principles.py")
run_scan = scan_mod.run_scan
EXIT_SUCCESS = scan_mod.EXIT_SUCCESS
EXIT_VIOLATIONS = scan_mod.EXIT_VIOLATIONS
EXIT_ERROR = scan_mod.EXIT_ERROR
main = scan_mod.main


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, encoding="utf-8")


def _make_repo_with_diff(repo: Path) -> None:
    """Create a minimal git repo on a feature branch with one changed file."""
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


class TestParseHunkHeader:
    """Unit tests for _parse_hunk_header."""

    def test_standard_hunk(self) -> None:
        start, count = _parse_hunk_header("@@ -1,3 +1,4 @@ def foo():")
        assert start == 1
        assert count == 4

    def test_single_line_implicit_count(self) -> None:
        # @@ -1 +1 @@ means one line added (count defaults to 1)
        start, count = _parse_hunk_header("@@ -1 +1 @@")
        assert start == 1
        assert count == 1

    def test_explicit_zero_count(self) -> None:
        # @@ ... +5,0 @@ means pure deletion starting at line 5 (0 new lines)
        start, count = _parse_hunk_header("@@ -5,3 +5,0 @@")
        assert start == 5
        assert count == 0

    def test_no_match_returns_zero(self) -> None:
        start, count = _parse_hunk_header("not a hunk header")
        assert start == 0
        assert count == 0

    def test_large_line_numbers(self) -> None:
        start, count = _parse_hunk_header("@@ -1000,5 +2000,10 @@")
        assert start == 2000
        assert count == 10


class TestRunGitDiff:
    """Unit tests for _run_git_diff error handling."""

    def test_raises_on_empty_base(self) -> None:
        with pytest.raises(ValueError):
            _run_git_diff("")

    def test_raises_on_dash_base(self) -> None:
        with pytest.raises(ValueError):
            _run_git_diff("--evil")

    def test_raises_when_git_missing(self) -> None:
        with patch.object(core.subprocess, "run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="git is not available"):
                _run_git_diff("main")

    def test_raises_on_timeout(self) -> None:
        with patch.object(
            core.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=30),
        ):
            with pytest.raises(RuntimeError, match="timed out"):
                _run_git_diff("main")

    def test_raises_on_nonzero_exit(self) -> None:
        err = subprocess.CalledProcessError(returncode=128, cmd="git")
        with patch.object(core.subprocess, "run", side_effect=err):
            with pytest.raises(RuntimeError, match="failed"):
                _run_git_diff("main")


class TestGetDiffLineNumbers:
    """Unit tests for get_diff_line_numbers."""

    def test_empty_base_returns_empty_dict(self) -> None:
        result = get_diff_line_numbers("")
        assert result == {}

    def test_parses_added_lines(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = get_diff_line_numbers("main")
        assert len(result) == 1
        key = next(iter(result))
        assert key.endswith("changed.py")
        assert 1 in result[key]

    def test_traversal_path_excluded(self) -> None:
        diff_text = (
            "diff --git a/../escape.py b/../escape.py\n"
            "--- a/../escape.py\n"
            "+++ b/../escape.py\n"
            "@@ -0,0 +1 @@\n"
            "+bad\n"
        )
        with (
            patch.object(core, "_git_root", return_value="/repo"),
            patch.object(core, "_run_git_diff", return_value=diff_text),
        ):
            result = get_diff_line_numbers("main")
        assert result == {}

    def test_removed_lines_not_counted(self) -> None:
        diff_text = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -2,3 +2,1 @@\n"
            " context\n"
            "-removed\n"
            "-removed2\n"
            "+added\n"
        )
        with (
            patch.object(core, "_git_root", return_value="/repo"),
            patch.object(core, "_run_git_diff", return_value=diff_text),
            patch.object(core, "is_safe_path", return_value=True),
        ):
            result = get_diff_line_numbers("main")
        key = "/repo/a.py"
        assert key in result
        assert 2 in result[key]  # context line
        assert 3 in result[key]  # added line
        assert 4 not in result[key]  # only 3 new lines: context(2), added(3)

    def test_multiple_hunks_merged(self) -> None:
        diff_text = (
            "diff --git a/f.py b/f.py\n"
            "--- a/f.py\n"
            "+++ b/f.py\n"
            "@@ -1 +1 @@\n"
            "+line1\n"
            "@@ -10 +10 @@\n"
            "+line10\n"
        )
        with (
            patch.object(core, "_git_root", return_value="/repo"),
            patch.object(core, "_run_git_diff", return_value=diff_text),
            patch.object(core, "is_safe_path", return_value=True),
        ):
            result = get_diff_line_numbers("main")
        assert "/repo/f.py" in result
        assert 1 in result["/repo/f.py"]
        assert 10 in result["/repo/f.py"]


class TestDiffScopeLineFiltering:
    """Integration tests: pre-existing violations suppressed, new ones reported."""

    def test_preexisting_violation_suppressed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A shell script on main that is NOT in the diff must not be reported."""
        _make_repo_with_diff(tmp_path)
        # legacy.sh exists on main (pre-existing) but is not in the feature diff.
        (tmp_path / "legacy.sh").write_text("echo legacy\n")
        _run_git(tmp_path, "checkout", "main")
        _run_git(tmp_path, "add", "legacy.sh")
        _run_git(tmp_path, "commit", "-m", "legacy shell on main")
        _run_git(tmp_path, "checkout", "feature")
        _run_git(tmp_path, "rebase", "main")
        monkeypatch.chdir(tmp_path)

        diff_lines = get_diff_line_numbers("main")
        from scan_principles_core import get_diff_files

        files = get_diff_files("main")
        from scan_principles_core import ALL_RULES

        result = run_scan(files, ALL_RULES, diff_lines)
        legacy = str(tmp_path / "legacy.sh")
        reported = [v.file for v in result.violations]
        assert legacy not in reported, "pre-existing legacy.sh must be suppressed"

    def test_new_violation_on_changed_line_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A shell script added in the diff must still be flagged (positive control)."""
        _make_repo_with_diff(tmp_path)
        (tmp_path / "added.sh").write_text("echo added\n")
        _run_git(tmp_path, "add", "added.sh")
        _run_git(tmp_path, "commit", "-m", "add shell script in diff")
        monkeypatch.chdir(tmp_path)

        diff_lines = get_diff_line_numbers("main")
        from scan_principles_core import ALL_RULES, get_diff_files

        files = get_diff_files("main")
        result = run_scan(files, ALL_RULES, diff_lines)
        added = str(tmp_path / "added.sh")
        reported = [v.file for v in result.violations]
        assert added in reported, "violation on a changed file must still be reported"

    def test_none_diff_lines_reports_all(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When diff_lines is None (no --diff-scope), all violations are reported."""
        _make_repo_with_diff(tmp_path)
        (tmp_path / "added.sh").write_text("echo added\n")
        _run_git(tmp_path, "add", "added.sh")
        _run_git(tmp_path, "commit", "-m", "add shell script in diff")
        monkeypatch.chdir(tmp_path)

        from scan_principles_core import ALL_RULES, get_diff_files

        files = get_diff_files("main")
        result = run_scan(files, ALL_RULES, diff_lines=None)
        added = str(tmp_path / "added.sh")
        assert any(v.file == added for v in result.violations)

    def test_isolating_negative_control_diff_lines_param(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Removing the diff_lines parameter causes pre-existing violations to appear.

        This is the isolating negative control: it proves the diff_lines param
        is individually load-bearing for the suppression behaviour.  If run_scan
        accepted diff_lines but ignored it, this test would still pass -- which
        means a survivor here indicates the parameter is not wired up.
        """
        _make_repo_with_diff(tmp_path)
        # legacy.sh is pre-existing (on main, not in the feature diff)
        (tmp_path / "legacy.sh").write_text("echo legacy\n")
        _run_git(tmp_path, "checkout", "main")
        _run_git(tmp_path, "add", "legacy.sh")
        _run_git(tmp_path, "commit", "-m", "legacy shell on main")
        _run_git(tmp_path, "checkout", "feature")
        _run_git(tmp_path, "rebase", "main")
        monkeypatch.chdir(tmp_path)

        from scan_principles_core import ALL_RULES, get_diff_files

        files = get_diff_files("main")
        # Pass diff_lines=None: legacy.sh IS in the file list and is scanned
        # without filtering, so the violation must appear.
        result_no_filter = run_scan(files + [str(tmp_path / "legacy.sh")], ALL_RULES, None)
        legacy = str(tmp_path / "legacy.sh")
        assert any(
            v.file == legacy for v in result_no_filter.violations
        ), "without filtering, legacy.sh violation must be present"

    def test_file_not_in_diff_lines_is_suppressed_when_explicitly_scanned(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A file explicitly passed to run_scan but absent from diff_lines is suppressed.

        This is the isolating negative control for the 'elif diff_lines is not None:
        violations = []' branch.  The test passes a pre-existing shell script directly
        to run_scan alongside a non-empty diff_lines dict that does NOT include that file.
        The violation must be empty because the file was not changed in the diff.

        If run_scan ignored the elif branch, this test would fail (violation appears).
        """
        _make_repo_with_diff(tmp_path)
        (tmp_path / "legacy.sh").write_text("echo legacy\n")
        monkeypatch.chdir(tmp_path)

        from scan_principles_core import ALL_RULES

        # diff_lines has an entry for a different file, not legacy.sh
        other_file = str(tmp_path / "other.py")
        diff_lines_with_other: dict[str, set[int]] = {other_file: {1, 2}}
        result = run_scan([str(tmp_path / "legacy.sh")], ALL_RULES, diff_lines_with_other)
        legacy = str(tmp_path / "legacy.sh")
        assert not any(
            v.file == legacy for v in result.violations
        ), "legacy.sh not in diff_lines must be suppressed even when explicitly scanned"
