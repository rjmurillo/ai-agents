"""Tests for _changed_files_against_base using three-dot diff (issue #4474).

Before the fix, the function used ``git diff --name-only base_ref`` (two-dot),
which compares the working tree directly to base_ref.  After a ``git merge
origin/main`` where main has advanced since the merge, the two-dot diff
runs in the wrong direction and includes main-side changes as apparent branch
changes, causing false semantic-conflict failures.

The fix changes the command to ``git diff --name-only base_ref...HEAD``
(three-dot), which always diffs from the merge-base to HEAD regardless of how
far base_ref has advanced.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
sys.path.insert(0, str(_VALIDATION))

import check_skill_md_portability as cmp


def _init_repo(root: Path) -> None:
    """Initialise an empty git repo with a first commit."""
    for args in (
        ("init", "-q", "-b", "main"),
        ("-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "--allow-empty", "-m", "init"),
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(root), *args],
        check=True,
        capture_output=True,
    )


class TestChangedFilesAgainstBaseThreeDot:
    """_changed_files_against_base uses the merge base, not base_ref tip."""

    def test_branch_files_returned_when_base_is_ancestor(self, tmp_path: Path) -> None:
        """Positive: files changed only on the branch appear in the result."""
        _init_repo(tmp_path)
        (tmp_path / "branch_file.md").write_text("content\n", encoding="utf-8")
        _git(tmp_path, "add", "branch_file.md")
        _git(tmp_path, "commit", "-m", "branch change")

        base_ref = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD~1"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()

        result = cmp._changed_files_against_base(tmp_path, base_ref)

        assert result is not None
        assert "branch_file.md" in result

    def test_main_only_files_excluded_when_base_advanced(self, tmp_path: Path) -> None:
        """Positive: files that exist only on main (not touched by the branch)
        do NOT appear in the result even when base_ref has advanced past the
        merge point.

        This is the #4474 scenario: main advances after the local merge.
        Three-dot diff uses the merge-base, so main-only changes are invisible.
        """
        _init_repo(tmp_path)

        # Simulate 'origin/main' advancing: write a file only main will touch.
        (tmp_path / "main_only.md").write_text("main content\n", encoding="utf-8")
        _git(tmp_path, "add", "main_only.md")
        _git(tmp_path, "commit", "-m", "main advance")
        main_advanced = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()

        # Create a branch diverging from the commit BEFORE main advanced.
        merge_base = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD~1"],
            check=True, capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()
        _git(tmp_path, "checkout", "-b", "feature", merge_base)
        (tmp_path / "branch_file.md").write_text("branch content\n", encoding="utf-8")
        _git(tmp_path, "add", "branch_file.md")
        _git(tmp_path, "commit", "-m", "branch change")

        # Pass the advanced main ref as base_ref (the #4474 scenario).
        result = cmp._changed_files_against_base(tmp_path, main_advanced)

        assert result is not None
        # Branch file is included.
        assert "branch_file.md" in result
        # Main-only file is NOT included: three-dot diff excludes it.
        assert "main_only.md" not in result

    def test_bad_base_ref_returns_none(self, tmp_path: Path) -> None:
        """Negative: an unresolvable base ref returns None so callers fail closed."""
        _init_repo(tmp_path)

        result = cmp._changed_files_against_base(tmp_path, "refs/heads/nonexistent")

        assert result is None

    def test_empty_diff_returns_empty_list(self, tmp_path: Path) -> None:
        """Edge: no changes between HEAD and base_ref returns an empty list, not None."""
        _init_repo(tmp_path)
        base_ref = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()

        result = cmp._changed_files_against_base(tmp_path, base_ref)

        assert result == []
