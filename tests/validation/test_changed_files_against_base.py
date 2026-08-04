"""Tests for _changed_files_against_base -- untracked-file detection (issue #4372).

The semantic-conflict guard calls ``_changed_files_against_base`` to decide
whether a baseline file was changed alongside a measured input.  Before the
fix, the function only called ``git diff --name-only`` which omits untracked
(not-yet-staged) files.  A newly created baseline that was never ``git add``ed
was therefore invisible to the guard, allowing a semantic conflict to slip
through.

The fix unions ``git diff`` output with ``git ls-files --others
--exclude-standard`` so an untracked baseline is included.

Platform note: all tests run on the current Linux host.  No Windows-specific
paths are exercised; that is noted where relevant.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"

import sys

sys.path.insert(0, str(_VALIDATION))

import check_skill_md_portability as cmp


class TestChangedFilesAgainstBase:
    """Tests for _changed_files_against_base (issue #4372)."""

    def test_tracked_changed_file_is_returned(self, tmp_path: Path) -> None:
        """A file reported by git diff --name-only is included."""
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            if "ls-files" in cmd:
                proc = subprocess.CompletedProcess(cmd, 0, "", "")
                proc.stdout = ""
                return proc
            proc = subprocess.CompletedProcess(cmd, 0, "", "")
            proc.stdout = "scripts/validation/portability.json\n"
            return proc

        with patch("subprocess.run", side_effect=fake_run):
            result = cmp._changed_files_against_base(tmp_path, "origin/main")

        assert result is not None
        assert "scripts/validation/portability.json" in result

    def test_untracked_new_file_is_returned(self, tmp_path: Path) -> None:
        """An untracked file (not staged) appears via git ls-files --others."""
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            if "ls-files" in cmd:
                proc = subprocess.CompletedProcess(cmd, 0, "", "")
                proc.stdout = ".portability-baseline.new.json\n"
                return proc
            # git diff returns nothing (no tracked changes)
            proc = subprocess.CompletedProcess(cmd, 0, "", "")
            proc.stdout = ""
            return proc

        with patch("subprocess.run", side_effect=fake_run):
            result = cmp._changed_files_against_base(tmp_path, "origin/main")

        assert result is not None
        assert ".portability-baseline.new.json" in result

    def test_union_of_tracked_and_untracked(self, tmp_path: Path) -> None:
        """Both tracked and untracked files appear in the result."""

        def fake_run(cmd, **kwargs):
            if "ls-files" in cmd:
                proc = subprocess.CompletedProcess(cmd, 0, "", "")
                proc.stdout = "new-baseline.json\n"
                return proc
            proc = subprocess.CompletedProcess(cmd, 0, "", "")
            proc.stdout = "existing.py\n"
            return proc

        with patch("subprocess.run", side_effect=fake_run):
            result = cmp._changed_files_against_base(tmp_path, "origin/main")

        assert result is not None
        assert "existing.py" in result
        assert "new-baseline.json" in result

    def test_no_duplicates_when_file_appears_in_both(self, tmp_path: Path) -> None:
        """A file staged and untracked simultaneously is listed once."""

        def fake_run(cmd, **kwargs):
            if "ls-files" in cmd:
                proc = subprocess.CompletedProcess(cmd, 0, "", "")
                proc.stdout = "shared.py\n"
                return proc
            proc = subprocess.CompletedProcess(cmd, 0, "", "")
            proc.stdout = "shared.py\n"
            return proc

        with patch("subprocess.run", side_effect=fake_run):
            result = cmp._changed_files_against_base(tmp_path, "origin/main")

        assert result is not None
        assert result.count("shared.py") == 1

    def test_returns_none_when_git_diff_fails(self, tmp_path: Path) -> None:
        """Returns None when git diff exits non-zero (fail-closed behaviour)."""

        def fake_run(cmd, **kwargs):
            if "ls-files" in cmd:
                proc = subprocess.CompletedProcess(cmd, 0, "", "")
                proc.stdout = ""
                return proc
            proc = subprocess.CompletedProcess(cmd, 128, "", "fatal: not a git repo")
            proc.stdout = ""
            return proc

        with patch("subprocess.run", side_effect=fake_run):
            result = cmp._changed_files_against_base(tmp_path, "origin/main")

        assert result is None

    def test_returns_empty_list_when_no_changes_and_no_untracked(
        self, tmp_path: Path
    ) -> None:
        """Returns [] when the tree is clean and nothing is untracked."""

        def fake_run(cmd, **kwargs):
            proc = subprocess.CompletedProcess(cmd, 0, "", "")
            proc.stdout = ""
            return proc

        with patch("subprocess.run", side_effect=fake_run):
            result = cmp._changed_files_against_base(tmp_path, "origin/main")

        assert result == []

    def test_ls_files_failure_is_tolerated(self, tmp_path: Path) -> None:
        """If git ls-files fails, tracked changes are still returned."""

        def fake_run(cmd, **kwargs):
            if "ls-files" in cmd:
                raise OSError("git ls-files not available")
            proc = subprocess.CompletedProcess(cmd, 0, "", "")
            proc.stdout = "tracked.py\n"
            return proc

        with patch("subprocess.run", side_effect=fake_run):
            result = cmp._changed_files_against_base(tmp_path, "origin/main")

        assert result is not None
        assert "tracked.py" in result
