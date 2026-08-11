"""The remaining repo-root walker must skip registered worktrees.

A registered worktree holds a full second copy of the tree. The no-verify gate
walked the repository root without skipping worktrees, so it parsed duplicated
files and could time out. The duplicate-helper gate is now git-scoped, and the
obsolete filesystem unreachable scanner was deleted.

This is the same bug issue #4160 fixed in `_python_sources`, recurring in
siblings that did not inherit the fix. Both halves of that fix are load
bearing and both are asserted here:

1. `worktrees` is in the skip set at all.
2. The skip is matched against the path *relative to the walk root*. Matching
   absolute parts makes the gate a silent no-op when the repository itself
   lives under a directory named `worktrees`, which is exactly how fleet
   worktrees are laid out.

Test outcomes:
    pass - every walker skips worktrees and stays scoped to the walk root
    fail - a walker regressed
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import pytest

import tests.test_no_verify_prohibition as noverify


def _make_tree(root: Path) -> None:
    """Write one real source file and one decoy inside a worktree copy."""
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "worktrees" / "wt_a" / "scripts").mkdir(
        parents=True, exist_ok=True
    )


class TestNoVerifyWalker:
    """_instruction_files ignores worktree copies but not the real tree."""

    def test_worktree_file_is_excluded_and_real_file_kept(
        self, tmp_path: Path
    ) -> None:
        _make_tree(tmp_path)
        claude = tmp_path / ".claude"
        real = claude / "real.md"
        real.write_text("plain instruction text\n")
        decoy = claude / "worktrees" / "wt_a" / "decoy.md"
        decoy.write_text("plain instruction text\n")

        with (
            patch.object(noverify, "REPO_ROOT", tmp_path),
            patch.object(noverify, "_INSTRUCTION_ROOTS", (".claude",)),
        ):
            files = noverify._instruction_files()

        assert real in files, f"real instruction file dropped; got {files}"
        assert decoy not in files, f"worktree copy should be excluded; got {files}"

    def test_root_named_worktrees_keeps_its_files(self, tmp_path: Path) -> None:
        """Issue #4160: matching absolute parts excludes the whole repository.

        Without this the walker looks fixed. Adding `worktrees` to the skip
        while still matching absolute parts makes the gate return nothing at
        all for a repository that lives under a directory named `worktrees`,
        which is how fleet worktrees are laid out. A gate that scans nothing
        passes, so the failure is silent.
        """
        root = tmp_path / "worktrees" / "wt_fix"
        claude = root / ".claude"
        claude.mkdir(parents=True, exist_ok=True)
        real = claude / "real.md"
        real.write_text("plain instruction text\n")

        with (
            patch.object(noverify, "REPO_ROOT", root),
            patch.object(noverify, "_INSTRUCTION_ROOTS", (".claude",)),
        ):
            files = noverify._instruction_files()

        assert real in files, (
            "a repository under a 'worktrees' dir must still be scanned; "
            f"got {files}"
        )


class TestNoTrackedFileHidesBehindTheSkip:
    """The skip is a blind spot only if a tracked file ever moves into it.

    Skipping any component named `worktrees` matches the repository's existing
    convention in `_python_sources`, so it stays. The cost is that a tracked
    file added under, say, `docs/worktrees/` would escape both gates without
    anyone noticing. This turns that silent hole into a loud failure at the
    moment someone digs it.
    """

    _KNOWN = frozenset({".agents/projects/v0.3.0/worktrees/.gitkeep"})

    @pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
    def test_no_new_tracked_path_lands_under_a_worktrees_dir(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo,
            capture_output=True,
            check=True,
            encoding="utf-8",
            errors="replace",
        ).stdout
        offenders = sorted(
            f
            for f in out.split("\0")
            if f and "worktrees" in PurePosixPath(f).parts and f not in self._KNOWN
        )

        assert offenders == [], (
            "These tracked files sit under a directory named 'worktrees', so "
            "the no-verify gate skips them silently. Either "
            "rename the directory or add the path to _KNOWN with a reason: "
            f"{offenders}"
        )


if __name__ == "__main__":  # pragma: no cover - manual smoke run
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
