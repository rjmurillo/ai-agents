"""Tests for skill_registry module.

These tests verify the skill registry functionality that tracks skill metadata
and utilization across the project.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.skill_registry import (
    SkillMetadata,
    format_json,
    format_summary,
    infer_category,
    parse_yaml_frontmatter,
    scan_skills,
)


class TestParseYamlFrontmatter:
    """Tests for parse_yaml_frontmatter function."""

    def test_parses_simple_frontmatter(self) -> None:
        """Parses basic YAML frontmatter."""
        content = """---
name: test-skill
description: A test skill
version: 1.0.0
---

# Test Skill
"""
        result = parse_yaml_frontmatter(content)

        assert result["name"] == "test-skill"
        assert result["description"] == "A test skill"
        assert result["version"] == "1.0.0"

    def test_handles_quoted_values(self) -> None:
        """Handles quoted string values."""
        content = """---
name: "quoted-name"
description: 'single quoted'
---
"""
        result = parse_yaml_frontmatter(content)

        assert result["name"] == "quoted-name"
        assert result["description"] == "single quoted"

    def test_returns_empty_dict_without_frontmatter(self) -> None:
        """Returns empty dict when no frontmatter present."""
        content = "# No frontmatter here"
        result = parse_yaml_frontmatter(content)

        assert result == {}

    def test_handles_empty_content(self) -> None:
        """Handles empty content gracefully."""
        result = parse_yaml_frontmatter("")

        assert result == {}


class TestInferCategory:
    """Tests for infer_category function."""

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("github-actions", "github"),
            ("pr-review", "github"),
            ("session-init", "workflow"),
            ("memory-sync", "memory"),
            ("security-scan", "security"),
            ("doc-coverage", "documentation"),
            ("adr-review", "architecture"),
            ("qa-checklist", "quality"),
            ("roadmap-planner", "planning"),
            ("unknown-skill", "utility"),
        ],
    )
    def test_infers_category_from_name(self, name: str, expected: str) -> None:
        """Infers correct category from skill name."""
        result = infer_category(name, "")

        assert result == expected

    def test_infers_from_description_when_name_unclear(self) -> None:
        """Uses description for category inference when name is generic."""
        result = infer_category("helper-tool", "Analyze code quality")

        assert result == "analysis"


class TestScanSkills:
    """Tests for scan_skills function."""

    @pytest.fixture
    def skills_dir(self, tmp_path: Path) -> Path:
        """Create a mock skills directory structure."""
        skills = tmp_path / "skills"
        skills.mkdir()

        # Create skill with SKILL.md
        skill1 = skills / "test-skill"
        skill1.mkdir()
        (skill1 / "SKILL.md").write_text("""---
name: test-skill
description: A test skill for testing
version: 1.0.0
model: claude-sonnet-4-5
---

# Test Skill
""")

        # Create skill without SKILL.md
        skill2 = skills / "no-metadata"
        skill2.mkdir()

        # Create hidden directory (should be skipped)
        hidden = skills / ".hidden"
        hidden.mkdir()

        return skills

    def test_scans_skills_directory(self, skills_dir: Path) -> None:
        """Scans skills directory and returns metadata."""
        result = scan_skills(skills_dir)

        assert len(result) == 2
        names = {s.name for s in result}
        assert "test-skill" in names
        assert "no-metadata" in names

    def test_extracts_frontmatter_metadata(self, skills_dir: Path) -> None:
        """Extracts metadata from SKILL.md frontmatter."""
        result = scan_skills(skills_dir)

        skill = next(s for s in result if s.name == "test-skill")
        assert skill.description == "A test skill for testing"
        assert skill.version == "1.0.0"
        assert skill.model == "claude-sonnet-4-5"

    def test_handles_missing_skill_md(self, skills_dir: Path) -> None:
        """Handles skills without SKILL.md gracefully."""
        result = scan_skills(skills_dir)

        skill = next(s for s in result if s.name == "no-metadata")
        assert skill.description == "No SKILL.md found"
        assert skill.category == "uncategorized"

    def test_skips_hidden_directories(self, skills_dir: Path) -> None:
        """Skips hidden directories."""
        result = scan_skills(skills_dir)

        names = {s.name for s in result}
        assert ".hidden" not in names

    def test_returns_empty_list_for_missing_directory(self, tmp_path: Path) -> None:
        """Returns empty list if skills directory does not exist."""
        result = scan_skills(tmp_path / "nonexistent")

        assert result == []


class TestFormatSummary:
    """Tests for format_summary function."""

    def test_formats_skills_by_category(self) -> None:
        """Groups skills by category in output."""
        skills = [
            SkillMetadata(name="github-pr", path=Path("."), category="github"),
            SkillMetadata(name="session-init", path=Path("."), category="workflow"),
        ]

        result = format_summary(skills)

        assert "## Github" in result
        assert "## Workflow" in result
        assert "github-pr" in result
        assert "session-init" in result

    def test_shows_skill_count(self) -> None:
        """Shows total skill count in header."""
        skills = [
            SkillMetadata(name="skill1", path=Path("."), category="utility"),
            SkillMetadata(name="skill2", path=Path("."), category="utility"),
        ]

        result = format_summary(skills)

        assert "2 skills found" in result


class TestFormatJson:
    """Tests for format_json function."""

    def test_outputs_valid_json(self) -> None:
        """Outputs valid JSON."""
        import json

        skills = [
            SkillMetadata(name="test", path=Path("."), category="utility"),
        ]

        result = format_json(skills)

        parsed = json.loads(result)
        assert parsed["total_skills"] == 1
        assert "generated_at" in parsed

    def test_groups_by_category(self) -> None:
        """Groups skills by category in JSON output."""
        import json

        skills = [
            SkillMetadata(name="github-pr", path=Path("."), category="github"),
            SkillMetadata(name="github-issue", path=Path("."), category="github"),
            SkillMetadata(name="session", path=Path("."), category="workflow"),
        ]

        result = format_json(skills)

        parsed = json.loads(result)
        assert "github" in parsed["by_category"]
        assert len(parsed["by_category"]["github"]) == 2

    def test_identifies_underutilized(self) -> None:
        """Identifies underutilized skills."""
        import json

        skills = [
            SkillMetadata(name="active", path=Path("."), git_commits_30d=5),
            SkillMetadata(name="inactive", path=Path("."), git_commits_30d=0),
        ]

        result = format_json(skills)

        parsed = json.loads(result)
        assert "inactive" in parsed["underutilized"]
        assert "active" not in parsed["underutilized"]
