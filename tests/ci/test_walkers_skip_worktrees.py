"""Repo-root walkers must skip registered worktrees.

A registered worktree holds a full second copy of the tree. Three gates walked
the repository root without skipping them, so each parsed ~92,000 Python
files instead of ~6,800 and tripped a 120s timeout, blocking every push from a
clone that uses worktrees. Two are pytest gates; the third is the unreachable
statement scanner lefthook runs as `check_unreachable_after_terminator.py .`.

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

import scripts.validation.check_unreachable_after_terminator as unreachable
import tests.test_no_duplicate_module_level_defs as dupes
import tests.test_no_verify_prohibition as noverify


def _make_tree(root: Path) -> None:
    """Write one real source file and one decoy inside a worktree copy."""
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "worktrees" / "wt_a" / "scripts").mkdir(
        parents=True, exist_ok=True
    )


class TestDuplicateDefsWalker:
    """collect_duplicates ignores worktree copies but not the real tree."""

    def test_worktree_duplicate_is_not_reported(self, tmp_path: Path) -> None:
        _make_tree(tmp_path)
        decoy = tmp_path / ".claude" / "worktrees" / "wt_a" / "scripts" / "d.py"
        decoy.write_text("def f():\n    pass\n\n\ndef f():\n    pass\n")

        found = dupes.collect_duplicates(tmp_path)

        assert found == [], f"worktree copy should be skipped, got {found}"

    def test_real_duplicate_is_still_reported(self, tmp_path: Path) -> None:
        """Negative control: the gate still catches what it exists to catch."""
        _make_tree(tmp_path)
        real = tmp_path / "scripts" / "r.py"
        real.write_text("def g():\n    pass\n\n\ndef g():\n    pass\n")

        found = dupes.collect_duplicates(tmp_path)

        assert [p for p, _, _ in found] == [real], f"expected {real}, got {found}"

    def test_root_named_worktrees_is_not_skipped_whole(self, tmp_path: Path) -> None:
        """Issue #4160: skipping on absolute parts makes the gate a no-op."""
        root = tmp_path / "worktrees" / "wt_fix"
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        real = root / "scripts" / "r.py"
        real.write_text("def h():\n    pass\n\n\ndef h():\n    pass\n")

        found = dupes.collect_duplicates(root)

        assert [p for p, _, _ in found] == [real], (
            "repo living under a 'worktrees' dir must still be scanned; "
            f"got {found}"
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
            "the duplicate-defs and no-verify gates skip them silently. Either "
            "rename the directory or add the path to _KNOWN with a reason: "
            f"{offenders}"
        )


class TestUnreachableWalker:
    """The lefthook gate `check_unreachable_after_terminator.py .` walks the repo root."""

    def test_worktree_file_is_not_scanned(self, tmp_path: Path) -> None:
        real = tmp_path / "real.py"
        real.write_text("x = 1\n", encoding="utf-8")
        wt = tmp_path / "worktrees" / "wf_1" / "copy.py"
        wt.parent.mkdir(parents=True)
        wt.write_text("x = 1\n", encoding="utf-8")

        found = unreachable._iter_paths([tmp_path])

        assert real in found
        assert wt not in found

    def test_root_named_worktrees_keeps_its_files(self, tmp_path: Path) -> None:
        """The relative-parts half. Absolute matching would skip the root whole."""
        root = tmp_path / "worktrees"
        root.mkdir()
        kept = root / "real.py"
        kept.write_text("x = 1\n", encoding="utf-8")

        found = unreachable._iter_paths([root])

        assert found == [kept], f"walker went silent under a worktrees root, got {found}"

    def test_explicit_file_argument_is_never_skipped(self, tmp_path: Path) -> None:
        """A file named on the command line is scanned even inside a worktree."""
        wt = tmp_path / "worktrees" / "wf_1" / "copy.py"
        wt.parent.mkdir(parents=True)
        wt.write_text("x = 1\n", encoding="utf-8")

        assert unreachable._iter_paths([wt]) == [wt]


class TestSkipSetContract:
    """The skip constant itself carries worktrees."""

    def test_worktrees_in_skip_set(self) -> None:
        assert "worktrees" in dupes._SKIP

    def test_worktrees_in_unreachable_skip_set(self) -> None:
        assert "worktrees" in unreachable._SKIP


if __name__ == "__main__":  # pragma: no cover - manual smoke run
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
