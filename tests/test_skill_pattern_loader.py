#!/usr/bin/env python3
"""
Unit tests for skill_pattern_loader.py

Tests cover:
- SKILL.md trigger table parsing (standard tables, missing sections)
- Multi-source directory scanning with deduplication
- Cache freshness checking and invalidation
- Cache write/read roundtrip
- Detection map building (patterns, commands, identity mappings)

Run with: python3 -m pytest tests/test_skill_pattern_loader.py -v
"""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# Add .claude/hooks/Stop directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "Stop"))

from skill_pattern_loader import (
    build_detection_maps,
    load_skill_patterns,
    parse_skill_triggers,
    scan_skill_directories,
    _check_cache_freshness,
    _get_cache_path,
    _read_cache,
    _write_cache,
)


def _create_skill_md(skill_dir: Path, name: str, content: str) -> Path:
    """Helper to create a SKILL.md in a named skill directory."""
    d = skill_dir / name
    d.mkdir(parents=True, exist_ok=True)
    skill_md = d / "SKILL.md"
    skill_md.write_text(content, encoding="utf-8")
    return skill_md


GITHUB_SKILL_MD = """\
---
name: github
version: 3.1.0
---
# GitHub Skill

## Triggers

| Phrase | Operation |
|--------|-----------|
| `create a PR` | Create-PullRequest.ps1 |
| `check CI status for PR #123` | Get-PRChecks.ps1 |
| `close issue #123` | Close-Issue operations |

---

## Decision Tree
"""

REFLECT_SKILL_MD = """\
---
name: reflect
version: 1.0.0
---
# Reflect Skill

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `reflect on this session` | Extract learnings |
| `/reflect` | Full analysis |
| `learn from this mistake` | Capture corrections |

### HIGH Priority Triggers

| Trigger | Example |
|---------|---------|
| `no, that's wrong` | User correction |
"""

NO_TRIGGERS_SKILL_MD = """\
---
name: simple-skill
---
# Simple Skill

This skill has no triggers section at all.

## Usage

Just use it.
"""

SLASH_COMMAND_SKILL_MD = """\
---
name: session-init
---
# Session Init

## Triggers

| Phrase | Action |
|--------|--------|
| `/session-init` | Create new session log |
| `create session log` | Natural language activation |
| `start new session` | Alternative trigger |
"""


class TestParseSkillTriggers(unittest.TestCase):
    """Test parsing trigger phrases from SKILL.md files."""

    def test_standard_table(self):
        """Standard trigger table with backtick-wrapped phrases."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_md = _create_skill_md(Path(tmpdir), "github", GITHUB_SKILL_MD)
            result = parse_skill_triggers(skill_md)

        self.assertEqual(result["name"], "github")
        self.assertIn("create a PR", result["triggers"])
        self.assertIn("check CI status for PR #123", result["triggers"])
        self.assertIn("close issue #123", result["triggers"])
        self.assertEqual(len(result["slash_commands"]), 0)

    def test_multiple_trigger_sections(self):
        """Skill with main Triggers section and sub-sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_md = _create_skill_md(Path(tmpdir), "reflect", REFLECT_SKILL_MD)
            result = parse_skill_triggers(skill_md)

        self.assertEqual(result["name"], "reflect")
        self.assertIn("reflect on this session", result["triggers"])
        self.assertIn("/reflect", result["triggers"])
        self.assertIn("learn from this mistake", result["triggers"])
        # HIGH Priority Triggers sub-section
        self.assertIn("no, that's wrong", result["triggers"])

    def test_no_triggers_section(self):
        """Skill without a Triggers section returns empty triggers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_md = _create_skill_md(Path(tmpdir), "simple-skill", NO_TRIGGERS_SKILL_MD)
            result = parse_skill_triggers(skill_md)

        self.assertEqual(result["name"], "simple-skill")
        self.assertEqual(result["triggers"], [])
        self.assertEqual(result["slash_commands"], [])

    def test_slash_commands_extracted(self):
        """Slash commands (phrases starting with /) are identified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_md = _create_skill_md(Path(tmpdir), "session-init", SLASH_COMMAND_SKILL_MD)
            result = parse_skill_triggers(skill_md)

        self.assertEqual(result["name"], "session-init")
        self.assertIn("/session-init", result["slash_commands"])
        self.assertNotIn("create session log", result["slash_commands"])

    def test_name_fallback_to_directory(self):
        """When frontmatter has no name, use directory name."""
        content = "# Skill\n\n## Triggers\n\n| Phrase |\n|--------|\n| `test` |\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_md = _create_skill_md(Path(tmpdir), "my-dir-name", content)
            result = parse_skill_triggers(skill_md)

        self.assertEqual(result["name"], "my-dir-name")

    def test_nonexistent_file(self):
        """Nonexistent file returns empty triggers with directory name."""
        result = parse_skill_triggers(Path("/nonexistent/skill-x/SKILL.md"))
        self.assertEqual(result["name"], "skill-x")  # parent directory name
        self.assertEqual(result["triggers"], [])


class TestScanSkillDirectories(unittest.TestCase):
    """Test multi-source directory scanning."""

    def test_scan_repo_skills(self):
        """Scan finds SKILL.md files in repo .claude/skills/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            skills_dir = project / ".claude" / "skills"
            _create_skill_md(skills_dir, "github", GITHUB_SKILL_MD)
            _create_skill_md(skills_dir, "reflect", REFLECT_SKILL_MD)

            result = scan_skill_directories(project)

        names = [p.parent.name for p in result]
        self.assertIn("github", names)
        self.assertIn("reflect", names)

    def test_deduplication_repo_wins(self):
        """Repo-level skills take priority over user-level for same name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            # Create repo-level skill
            repo_skills = project / ".claude" / "skills"
            _create_skill_md(repo_skills, "github", GITHUB_SKILL_MD)

            # Create user-level skill at same name (simulate ~/.claude/skills)
            # We can't easily mock Path.home(), so instead we test the
            # deduplication logic by checking repo skill is found first
            result = scan_skill_directories(project)

        github_paths = [p for p in result if p.parent.name == "github"]
        self.assertEqual(len(github_paths), 1)
        self.assertTrue(str(github_paths[0]).startswith(str(project)))

    def test_missing_directories_handled(self):
        """Missing skill directories are silently skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            # No .claude/skills/ directory created
            result = scan_skill_directories(project)

        # Should not raise, may find user-level skills but won't find repo skills
        self.assertIsInstance(result, list)

    def test_case_insensitive_glob(self):
        """Both SKILL.md and skill.md are found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            skills_dir = project / ".claude" / "skills"

            # Create one with SKILL.md (standard)
            _create_skill_md(skills_dir, "github", GITHUB_SKILL_MD)

            # Create one with skill.md (lowercase)
            lower_dir = skills_dir / "lowercase-skill"
            lower_dir.mkdir(parents=True, exist_ok=True)
            (lower_dir / "skill.md").write_text(NO_TRIGGERS_SKILL_MD, encoding="utf-8")

            result = scan_skill_directories(project)

        names = [p.parent.name for p in result]
        self.assertIn("github", names)
        self.assertIn("lowercase-skill", names)

    def test_github_skills_source(self):
        """Scan finds skills in .github/skills/ path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            github_skills = project / ".github" / "skills"
            _create_skill_md(github_skills, "copilot-skill", GITHUB_SKILL_MD)

            result = scan_skill_directories(project)

        names = [p.parent.name for p in result]
        self.assertIn("copilot-skill", names)


class TestBuildDetectionMaps(unittest.TestCase):
    """Test building detection maps from parsed skill data."""

    def test_includes_name_and_path(self):
        """Patterns include skill name and .claude/skills/{name} path."""
        skills = [{
            "name": "github",
            "triggers": ["create a PR", "gh pr"],
            "slash_commands": [],
        }]
        patterns, _ = build_detection_maps(skills)

        self.assertIn("github", patterns)
        self.assertIn("github", patterns["github"])
        self.assertIn(".claude/skills/github", patterns["github"])
        self.assertIn("create a PR", patterns["github"])

    def test_slash_commands_mapped(self):
        """Slash commands create command_to_skill mappings."""
        skills = [{
            "name": "session-init",
            "triggers": ["/session-init", "create session log"],
            "slash_commands": ["/session-init"],
        }]
        _, commands = build_detection_maps(skills)

        self.assertEqual(commands["session-init"], "session-init")

    def test_identity_mapping_auto_added(self):
        """Skill name is auto-added as identity mapping in command_to_skill."""
        skills = [{
            "name": "reflect",
            "triggers": ["reflect on this"],
            "slash_commands": [],
        }]
        _, commands = build_detection_maps(skills)

        self.assertEqual(commands["reflect"], "reflect")

    def test_deduplication(self):
        """Duplicate patterns are removed."""
        skills = [{
            "name": "test-skill",
            "triggers": ["test-skill", "test-skill", "do test"],
            "slash_commands": [],
        }]
        patterns, _ = build_detection_maps(skills)

        # "test-skill" should appear once (from triggers) + ".claude/skills/test-skill"
        test_patterns = patterns["test-skill"]
        count = sum(1 for p in test_patterns if p.lower() == "test-skill")
        self.assertEqual(count, 1, "Duplicate patterns should be deduplicated")

    def test_multiple_skills(self):
        """Multiple skills produce separate pattern entries."""
        skills = [
            {"name": "github", "triggers": ["gh pr"], "slash_commands": []},
            {"name": "reflect", "triggers": ["/reflect"], "slash_commands": ["/reflect"]},
        ]
        patterns, commands = build_detection_maps(skills)

        self.assertIn("github", patterns)
        self.assertIn("reflect", patterns)
        self.assertEqual(commands["reflect"], "reflect")


class TestCacheFreshness(unittest.TestCase):
    """Test stat-based cache invalidation."""

    def test_fresh_cache_returns_true(self):
        """Cache with matching mtimes is considered fresh."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.md"
            f.write_text("content", encoding="utf-8")

            cache_data = {
                "source_mtimes": {str(f): f.stat().st_mtime},
            }
            self.assertTrue(_check_cache_freshness(cache_data, [f]))

    def test_stale_cache_after_modification(self):
        """Cache is stale when a source file is modified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.md"
            f.write_text("content", encoding="utf-8")
            old_mtime = f.stat().st_mtime

            cache_data = {
                "source_mtimes": {str(f): old_mtime},
            }

            # Modify file to change mtime
            time.sleep(0.05)
            f.write_text("modified content", encoding="utf-8")

            self.assertFalse(_check_cache_freshness(cache_data, [f]))

    def test_stale_cache_new_file_added(self):
        """Cache is stale when a new SKILL.md file appears."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "a.md"
            f1.write_text("a", encoding="utf-8")
            f2 = Path(tmpdir) / "b.md"
            f2.write_text("b", encoding="utf-8")

            # Cache only knows about f1
            cache_data = {
                "source_mtimes": {str(f1): f1.stat().st_mtime},
            }

            # Current files include both
            self.assertFalse(_check_cache_freshness(cache_data, [f1, f2]))

    def test_stale_cache_file_removed(self):
        """Cache is stale when a tracked SKILL.md file is deleted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "a.md"
            f1.write_text("a", encoding="utf-8")

            cache_data = {
                "source_mtimes": {
                    str(f1): f1.stat().st_mtime,
                    str(Path(tmpdir) / "gone.md"): 12345.0,
                },
            }

            # Only f1 exists now
            self.assertFalse(_check_cache_freshness(cache_data, [f1]))


class TestCacheRoundtrip(unittest.TestCase):
    """Test cache write/read roundtrip."""

    def test_write_read_roundtrip(self):
        """Written cache data can be read back correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            skill_file = Path(tmpdir) / "test.md"
            skill_file.write_text("content", encoding="utf-8")

            patterns = {"github": ["create a PR", "gh pr"]}
            commands = {"reflect": "reflect"}

            _write_cache(cache_path, [skill_file], patterns, commands)
            data = _read_cache(cache_path)

            self.assertIsNotNone(data)
            self.assertEqual(data["skill_patterns"], patterns)
            self.assertEqual(data["command_to_skill"], commands)
            self.assertEqual(data["version"], 1)
            self.assertIn(str(skill_file), data["source_mtimes"])

    def test_read_invalid_json(self):
        """Invalid JSON in cache file returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            cache_path.write_text("not json{{{", encoding="utf-8")

            self.assertIsNone(_read_cache(cache_path))

    def test_read_wrong_version(self):
        """Cache with wrong version returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            cache_path.write_text(json.dumps({
                "version": 999,
                "source_mtimes": {},
                "skill_patterns": {},
                "command_to_skill": {},
            }), encoding="utf-8")

            self.assertIsNone(_read_cache(cache_path))

    def test_read_missing_file(self):
        """Missing cache file returns None."""
        self.assertIsNone(_read_cache(Path("/nonexistent/cache.json")))


class TestLoadSkillPatterns(unittest.TestCase):
    """Integration test: full load_skill_patterns flow."""

    def test_loads_from_skill_md_files(self):
        """Patterns are loaded from real SKILL.md files in directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            skills_dir = project / ".claude" / "skills"
            _create_skill_md(skills_dir, "github", GITHUB_SKILL_MD)
            _create_skill_md(skills_dir, "session-init", SLASH_COMMAND_SKILL_MD)

            # Ensure cache directory exists
            (project / ".claude" / "hooks" / "Stop").mkdir(parents=True, exist_ok=True)

            patterns, commands = load_skill_patterns(project)

        self.assertIn("github", patterns)
        self.assertIn("create a PR", patterns["github"])
        self.assertIn("session-init", commands)

    def test_caches_results(self):
        """Second call uses cache (returns same data without re-parsing)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            skills_dir = project / ".claude" / "skills"
            _create_skill_md(skills_dir, "github", GITHUB_SKILL_MD)
            (project / ".claude" / "hooks" / "Stop").mkdir(parents=True, exist_ok=True)

            # First call: cold start
            patterns1, commands1 = load_skill_patterns(project)
            # Second call: should use cache
            patterns2, commands2 = load_skill_patterns(project)

            self.assertEqual(patterns1, patterns2)
            self.assertEqual(commands1, commands2)

            # Verify cache file exists
            cache_path = _get_cache_path(project)
            self.assertTrue(cache_path.exists())

    def test_empty_project_returns_empty_dicts(self):
        """Project with no skills returns empty dicts when user dirs also empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            # Mock Path.home() to an empty dir so user-level skills aren't found
            fake_home = Path(tmpdir) / "fakehome"
            fake_home.mkdir()
            with patch("skill_pattern_loader.Path.home", return_value=fake_home):
                patterns, commands = load_skill_patterns(project)

        self.assertEqual(patterns, {})
        self.assertEqual(commands, {})

    def test_invalidates_on_new_skill(self):
        """Adding a new SKILL.md invalidates the cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            skills_dir = project / ".claude" / "skills"
            _create_skill_md(skills_dir, "github", GITHUB_SKILL_MD)
            (project / ".claude" / "hooks" / "Stop").mkdir(parents=True, exist_ok=True)

            # First call: populate cache
            patterns1, _ = load_skill_patterns(project)
            self.assertNotIn("reflect", patterns1)

            # Add new skill
            time.sleep(0.05)
            _create_skill_md(skills_dir, "reflect", REFLECT_SKILL_MD)

            # Second call: cache should be invalidated
            patterns2, _ = load_skill_patterns(project)
            self.assertIn("reflect", patterns2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
