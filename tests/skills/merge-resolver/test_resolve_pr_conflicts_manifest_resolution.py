#!/usr/bin/env python3
"""Tests for plugin manifest version-conflict resolution against real git merge conflicts.

The ADR-091 versionless migration has its own module,
test_resolve_pr_conflicts_manifest_migration.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)
TESTS_MERGE_RESOLVER_DIR = str(Path(__file__).resolve().parent)
if TESTS_MERGE_RESOLVER_DIR not in sys.path:
    sys.path.insert(0, TESTS_MERGE_RESOLVER_DIR)

from claude_skills_import import import_skill_script
from manifest_conflict_fixtures import (
    MANIFEST,
    git,
    make_manifest_conflict,
    manifest_json,
)

mod = import_skill_script(".claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py")

resolve_plugin_manifest_conflict = mod.resolve_plugin_manifest_conflict

class TestResolvePluginManifestConflict:
    """Version-only conflicts resolve to one patch bump above the higher side."""

    def test_version_only_conflict_resolves_to_bumped_max(self, tmp_path: Path) -> None:
        make_manifest_conflict(
            tmp_path,
            base=manifest_json("0.5.1"),
            ours=manifest_json("0.5.2"),
            theirs=manifest_json("0.5.3"),
        )
        assert resolve_plugin_manifest_conflict(MANIFEST, cwd=str(tmp_path)) is True
        content = (tmp_path / MANIFEST).read_text(encoding="utf-8")
        assert '"version": "0.5.4"' in content
        assert "<<<<<<<" not in content
        staged = git(tmp_path, "diff", "--name-only", "--cached").stdout
        assert MANIFEST in staged
        unmerged = git(tmp_path, "diff", "--name-only", "--diff-filter=U").stdout
        assert MANIFEST not in unmerged

    def test_resolves_above_ours_when_ours_higher(self, tmp_path: Path) -> None:
        make_manifest_conflict(
            tmp_path,
            base=manifest_json("0.5.1"),
            ours=manifest_json("0.5.9"),
            theirs=manifest_json("0.5.3"),
        )
        assert resolve_plugin_manifest_conflict(MANIFEST, cwd=str(tmp_path)) is True
        content = (tmp_path / MANIFEST).read_text(encoding="utf-8")
        assert '"version": "0.5.10"' in content

    def test_non_version_difference_blocks(self, tmp_path: Path) -> None:
        make_manifest_conflict(
            tmp_path,
            base=manifest_json("0.5.1"),
            ours=manifest_json("0.5.2", description="changed on pr"),
            theirs=manifest_json("0.5.3"),
        )
        assert resolve_plugin_manifest_conflict(MANIFEST, cwd=str(tmp_path)) is False
        unmerged = git(tmp_path, "diff", "--name-only", "--diff-filter=U").stdout
        assert MANIFEST in unmerged

    def test_prerelease_version_blocks(self, tmp_path: Path) -> None:
        make_manifest_conflict(
            tmp_path,
            base=manifest_json("0.5.1"),
            ours=manifest_json("0.5.2"),
            theirs=manifest_json("0.6.0-rc.1"),
        )
        assert resolve_plugin_manifest_conflict(MANIFEST, cwd=str(tmp_path)) is False

    def test_malformed_json_blocks(self, tmp_path: Path) -> None:
        make_manifest_conflict(
            tmp_path,
            base=manifest_json("0.5.1"),
            ours='{"name": "broken",\n',
            theirs=manifest_json("0.5.3"),
        )
        assert resolve_plugin_manifest_conflict(MANIFEST, cwd=str(tmp_path)) is False

    def test_no_conflict_stages_returns_false(self, tmp_path: Path) -> None:
        git(tmp_path, "init", "-b", "main")
        assert resolve_plugin_manifest_conflict(MANIFEST, cwd=str(tmp_path)) is False
