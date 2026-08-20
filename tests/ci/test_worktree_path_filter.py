"""Tests for issue #4160: worktree path filter uses relative parts.

Bug: ``_python_sources()`` checked ``p.parts`` (absolute path components)
against the skip list. When the repo root was inside a directory named
``worktrees``, the skip string ``"worktrees"`` matched every file path and
the function returned an empty tuple.

Fix: check ``p.relative_to(_REPO_ROOT).parts`` so only path components
relative to the repo root are examined.
"""

from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import patch


def _import_module() -> types.ModuleType:
    """Return the test_validation_scripts_are_reachable module."""
    import tests.ci.test_validation_scripts_are_reachable as mod

    return mod


class TestWorktreePathFilter:
    """_python_sources uses relative path parts for skip filtering."""

    def test_file_inside_worktrees_root_is_discovered(self, tmp_path: Path) -> None:
        """A source file is found even when the repo root is inside a 'worktrees' dir."""
        # Simulate a repo root that lives inside a directory named "worktrees"
        fake_root = tmp_path / "worktrees" / "wt_fix"
        for subdir in ("scripts", ".claude/skills/merge-resolver/scripts", "tests"):
            (fake_root / subdir).mkdir(parents=True, exist_ok=True)
        probe = fake_root / "scripts" / "validate_worktree.py"
        probe.write_text("# placeholder\n")

        mod = _import_module()
        # Clear the lru_cache so the patched root takes effect
        mod._python_sources.cache_clear()
        try:
            with patch.object(mod, "_REPO_ROOT", fake_root):
                sources = mod._python_sources()
        finally:
            mod._python_sources.cache_clear()

        assert probe in sources, (
            f"Expected {probe} in _python_sources() but it was filtered out. "
            f"Got: {[str(s) for s in sources[:5]]}"
        )

    def test_file_under_relative_worktrees_subdir_is_excluded(self, tmp_path: Path) -> None:
        """A file whose RELATIVE path contains 'worktrees' is still excluded."""
        fake_root = tmp_path / "repo"
        # scripts/worktrees/helper.py -- "worktrees" in relative path
        bad_dir = fake_root / "scripts" / "worktrees"
        bad_dir.mkdir(parents=True)
        bad_file = bad_dir / "helper.py"
        bad_file.write_text("# should be excluded\n")
        # scripts/validate_ok.py -- no skip word in relative path
        ok_file = fake_root / "scripts" / "validate_ok.py"
        ok_file.write_text("# should be included\n")

        mod = _import_module()
        mod._python_sources.cache_clear()
        try:
            with patch.object(mod, "_REPO_ROOT", fake_root):
                sources = mod._python_sources()
        finally:
            mod._python_sources.cache_clear()

        assert bad_file not in sources, (
            f"{bad_file} should be excluded (relative path contains 'worktrees')"
        )
        assert ok_file in sources, (
            f"{ok_file} should be included (no skip word in relative path)"
        )

    def test_pycache_still_excluded_from_worktree_root(self, tmp_path: Path) -> None:
        """__pycache__ skip still applies even when repo root is inside worktrees."""
        fake_root = tmp_path / "worktrees" / "wt_fix"
        cache_dir = fake_root / "scripts" / "__pycache__"
        cache_dir.mkdir(parents=True)
        cached_py = cache_dir / "compiled.py"
        cached_py.write_text("# should be excluded\n")

        mod = _import_module()
        mod._python_sources.cache_clear()
        try:
            with patch.object(mod, "_REPO_ROOT", fake_root):
                sources = mod._python_sources()
        finally:
            mod._python_sources.cache_clear()

        assert cached_py not in sources

    def test_real_repo_root_not_under_worktrees_still_works(self, tmp_path: Path) -> None:
        """A standard repo root (no worktrees in its path) still discovers files."""
        fake_root = tmp_path / "ai-agents"
        scripts_dir = fake_root / "scripts"
        scripts_dir.mkdir(parents=True)
        normal = scripts_dir / "validate_something.py"
        normal.write_text("# normal\n")

        mod = _import_module()
        mod._python_sources.cache_clear()
        try:
            with patch.object(mod, "_REPO_ROOT", fake_root):
                sources = mod._python_sources()
        finally:
            mod._python_sources.cache_clear()

        assert normal in sources
