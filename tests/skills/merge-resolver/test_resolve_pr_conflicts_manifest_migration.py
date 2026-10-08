#!/usr/bin/env python3
"""Tests for the ADR-091 migration of plugin manifests to the versionless shape.

Covers real git merge conflicts where one side dropped the version field.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

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
    versionless_manifest_json,
)

mod = import_skill_script(".claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py")

resolve_plugin_manifest_conflict = mod.resolve_plugin_manifest_conflict
_resolve_conflicted_file = mod._resolve_conflicted_file

class TestResolvePluginManifestAdr091Migration:
    """A side that dropped the version field wins: ADR-092 forbids the field."""

    def test_main_dropped_version_resolves_to_versionless(self, tmp_path: Path) -> None:
        # The shape every plugin PR opened before ADR-092 hits on merging main.
        make_manifest_conflict(
            tmp_path,
            base=manifest_json("0.6.5448"),
            ours=manifest_json("0.6.5449"),
            theirs=versionless_manifest_json(),
        )
        assert resolve_plugin_manifest_conflict(MANIFEST, cwd=str(tmp_path)) is True
        content = (tmp_path / MANIFEST).read_text(encoding="utf-8")
        assert "version" not in json.loads(content)
        assert "<<<<<<<" not in content
        staged = git(tmp_path, "diff", "--name-only", "--cached").stdout
        assert MANIFEST in staged
        unmerged = git(tmp_path, "diff", "--name-only", "--diff-filter=U").stdout
        assert MANIFEST not in unmerged

    def test_branch_dropped_version_resolves_to_versionless(self, tmp_path: Path) -> None:
        # The rebase direction, where ours and theirs swap.
        make_manifest_conflict(
            tmp_path,
            base=manifest_json("0.6.5448"),
            ours=versionless_manifest_json(),
            theirs=manifest_json("0.6.5449"),
        )
        assert resolve_plugin_manifest_conflict(MANIFEST, cwd=str(tmp_path)) is True
        assert "version" not in json.loads((tmp_path / MANIFEST).read_text(encoding="utf-8"))

    def test_versionless_conflict_dispatches_as_resolved(self, tmp_path: Path) -> None:
        # The full dispatch path at a real plugin-root path, not just the
        # helper: pre-fix this returned "blocked" and every migrating PR
        # needed a hand edit.
        rooted = f".claude/{MANIFEST}"
        make_manifest_conflict(
            tmp_path,
            base=manifest_json("0.6.5448"),
            ours=manifest_json("0.6.5449"),
            theirs=versionless_manifest_json(),
            rel=rooted,
        )
        result: dict[str, Any] = {
            "success": False,
            "message": "",
            "files_resolved": [],
            "files_blocked": [],
        }
        status = _resolve_conflicted_file(rooted, result, cwd=str(tmp_path))
        assert status == "resolved"
        assert result["files_blocked"] == []
        assert result["files_resolved"] == [rooted]

    def test_versionless_with_other_difference_still_blocks(self, tmp_path: Path) -> None:
        make_manifest_conflict(
            tmp_path,
            base=manifest_json("0.6.5448"),
            ours=manifest_json("0.6.5449", description="changed on pr"),
            theirs=versionless_manifest_json(),
        )
        assert resolve_plugin_manifest_conflict(MANIFEST, cwd=str(tmp_path)) is False
        unmerged = git(tmp_path, "diff", "--name-only", "--diff-filter=U").stdout
        assert MANIFEST in unmerged
