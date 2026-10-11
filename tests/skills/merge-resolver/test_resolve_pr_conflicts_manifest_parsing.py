#!/usr/bin/env python3
"""Tests for plugin manifest detection and strict semver parsing in resolve_pr_conflicts.
"""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py")

is_plugin_manifest = mod.is_plugin_manifest
_parse_plain_semver = mod._parse_plain_semver

class TestIsPluginManifest:
    """Detection of packaged plugin manifests (issue #2543)."""

    def test_claude_plugin_manifest(self) -> None:
        assert is_plugin_manifest(".claude/.claude-plugin/plugin.json")

    def test_copilot_plugin_manifest(self) -> None:
        assert is_plugin_manifest("src/copilot-cli/.claude-plugin/plugin.json")

    def test_backslash_path_normalized(self) -> None:
        assert is_plugin_manifest(r".claude\.claude-plugin\plugin.json")

    def test_root_plugin_json_is_not_manifest(self) -> None:
        assert not is_plugin_manifest("plugin.json")

    def test_other_skill_files_are_not_manifests(self) -> None:
        assert not is_plugin_manifest(".claude/skills/github/SKILL.md")


class TestParsePlainSemver:
    """Strict MAJOR.MINOR.PATCH parsing; anything else falls back to manual."""

    def test_plain_version(self) -> None:
        assert _parse_plain_semver("0.5.168") == (0, 5, 168)

    def test_prerelease_rejected(self) -> None:
        assert _parse_plain_semver("0.6.0-rc.1") is None

    def test_build_metadata_rejected(self) -> None:
        assert _parse_plain_semver("0.6.0+build.5") is None

    def test_malformed_rejected(self) -> None:
        assert _parse_plain_semver("not-a-version") is None
