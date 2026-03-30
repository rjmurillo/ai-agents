"""Tests for skill_registry module.

Verifies skill scanning, frontmatter parsing, categorization, and output
formatting for the skill utilization tracking registry.

See: Issue #1266 - Implement skill utilization tracking
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.skill_registry import (
    SkillEntry,
    categorize_skill,
    format_json,
    format_markdown,
    main,
    parse_frontmatter,
    scan_skills,
)


class TestParseFrontmatter:
    """Tests for parse_frontmatter function."""

    def test_valid_frontmatter(self, tmp_path: Path) -> None:
        """Extracts key-value pairs from valid frontmatter."""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            "---\nname: test-skill\nversion: 1.0.0\nmodel: claude-sonnet-4-5\n"
            "description: A test skill\n---\n\nBody text here.\n"
        )

        result = parse_frontmatter(skill_md)

        assert result["name"] == "test-skill"
        assert result["version"] == "1.0.0"
        assert result["model"] == "claude-sonnet-4-5"
        assert result["description"] == "A test skill"

    def test_missing_opening_delimiter(self, tmp_path: Path) -> None:
        """Returns empty dict when file lacks opening ---."""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("name: test\n---\n")

        result = parse_frontmatter(skill_md)

        assert result == {}

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Returns empty dict for missing file."""
        result = parse_frontmatter(tmp_path / "nonexistent.md")

        assert result == {}

    def test_empty_file(self, tmp_path: Path) -> None:
        """Returns empty dict for empty file."""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("")

        result = parse_frontmatter(skill_md)

        assert result == {}

    def test_skips_lines_without_colon(self, tmp_path: Path) -> None:
        """Skips lines that are not key-value pairs."""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\nname: test\nno-value-here\n---\n")

        result = parse_frontmatter(skill_md)

        assert result == {"name": "test"}

    def test_skips_empty_values(self, tmp_path: Path) -> None:
        """Skips keys with empty values (nested YAML markers)."""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\nname: test\nmetadata:\n  nested: val\n---\n")

        result = parse_frontmatter(skill_md)

        assert "metadata" not in result
        assert result["name"] == "test"


class TestCategorizeSkill:
    """Tests for categorize_skill function."""

    def test_known_category(self) -> None:
        """Returns correct category for known skill names."""
        assert categorize_skill("session-init") == "session"
        assert categorize_skill("security-scan") == "security"
        assert categorize_skill("analyze") == "quality"
        assert categorize_skill("planner") == "planning"
        assert categorize_skill("github") == "github"

    def test_unknown_returns_other(self) -> None:
        """Returns 'other' for unrecognized skill names."""
        assert categorize_skill("unknown-skill") == "other"


class TestScanSkills:
    """Tests for scan_skills function."""

    @pytest.fixture()
    def skill_tree(self, tmp_path: Path) -> Path:
        """Create a minimal skills directory with two skills."""
        skills_dir = tmp_path / ".claude" / "skills"
        skills_dir.mkdir(parents=True)

        # Skill with frontmatter
        skill_a = skills_dir / "alpha"
        skill_a.mkdir()
        (skill_a / "SKILL.md").write_text(
            "---\nname: alpha\nversion: 2.0.0\ndescription: Alpha skill\n---\n"
        )

        # Skill without SKILL.md
        skill_b = skills_dir / "beta"
        skill_b.mkdir()

        # Non-directory file (should be skipped)
        (skills_dir / "CLAUDE.md").write_text("# Index\n")

        return tmp_path

    def test_finds_skill_directories(self, skill_tree: Path) -> None:
        """Discovers skill directories and skips files."""
        skills_dir = skill_tree / ".claude" / "skills"
        entries = scan_skills(skills_dir, skill_tree)

        names = [e.name for e in entries]
        assert "alpha" in names
        assert "beta" in names
        assert len(entries) == 2

    def test_extracts_frontmatter_metadata(self, skill_tree: Path) -> None:
        """Populates entry fields from frontmatter."""
        skills_dir = skill_tree / ".claude" / "skills"
        entries = scan_skills(skills_dir, skill_tree)

        alpha = next(e for e in entries if e.name == "alpha")
        assert alpha.version == "2.0.0"
        assert alpha.description == "Alpha skill"

    def test_handles_missing_skill_md(self, skill_tree: Path) -> None:
        """Falls back to directory name when SKILL.md is missing."""
        skills_dir = skill_tree / ".claude" / "skills"
        entries = scan_skills(skills_dir, skill_tree)

        beta = next(e for e in entries if e.name == "beta")
        assert beta.version == ""
        assert beta.description == ""


class TestFormatJson:
    """Tests for format_json function."""

    def test_produces_valid_json(self) -> None:
        """Output is valid JSON with expected structure."""
        entries = [
            SkillEntry(name="test", path=".claude/skills/test"),
        ]

        result = json.loads(format_json(entries))

        assert result["total_skills"] == 1
        assert result["skills"][0]["name"] == "test"
        assert "generated_at" in result

    def test_empty_list(self) -> None:
        """Handles empty entry list."""
        result = json.loads(format_json([]))

        assert result["total_skills"] == 0
        assert result["skills"] == []


class TestFormatMarkdown:
    """Tests for format_markdown function."""

    def test_contains_header(self) -> None:
        """Output includes skill count in header."""
        entries = [
            SkillEntry(
                name="test",
                path=".claude/skills/test",
                category="meta",
                last_commit_days_ago=5,
            ),
        ]

        result = format_markdown(entries, stale_days=30)

        assert "# Skill Registry (1 skills)" in result

    def test_stale_section_present_when_applicable(self) -> None:
        """Shows underutilized section when stale skills exist."""
        entries = [
            SkillEntry(
                name="old-skill",
                path=".claude/skills/old-skill",
                category="other",
                last_commit_days_ago=60,
            ),
        ]

        result = format_markdown(entries, stale_days=30)

        assert "Underutilized Skills" in result
        assert "old-skill" in result

    def test_no_stale_section_when_all_fresh(self) -> None:
        """Omits underutilized section when no stale skills."""
        entries = [
            SkillEntry(
                name="fresh",
                path=".claude/skills/fresh",
                category="meta",
                last_commit_days_ago=5,
            ),
        ]

        result = format_markdown(entries, stale_days=30)

        assert "Underutilized" not in result


class TestMain:
    """Tests for main entry point."""

    @pytest.fixture()
    def skill_tree(self, tmp_path: Path) -> Path:
        """Create minimal skills directory."""
        skills_dir = tmp_path / ".claude" / "skills"
        skill_a = skills_dir / "alpha"
        skill_a.mkdir(parents=True)
        (skill_a / "SKILL.md").write_text("---\nname: alpha\n---\n")
        return tmp_path

    def test_json_output_success(self, skill_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Returns 0 and outputs JSON for valid skills directory."""
        rc = main([
            "--format", "json",
            "--skills-dir", str(skill_tree / ".claude" / "skills"),
            "--project-root", str(skill_tree),
        ])
        captured = capsys.readouterr()

        assert rc == 0
        data = json.loads(captured.out)
        assert data["total_skills"] == 1

    def test_markdown_output_success(self, skill_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Returns 0 and outputs markdown for valid skills directory."""
        rc = main([
            "--format", "markdown",
            "--skills-dir", str(skill_tree / ".claude" / "skills"),
            "--project-root", str(skill_tree),
        ])
        captured = capsys.readouterr()

        assert rc == 0
        assert "# Skill Registry" in captured.out

    def test_missing_skills_dir_returns_error(self, tmp_path: Path) -> None:
        """Returns 1 when skills directory does not exist."""
        rc = main([
            "--skills-dir", str(tmp_path / "nonexistent"),
            "--project-root", str(tmp_path),
        ])

        assert rc == 1

    def test_output_to_file(self, skill_tree: Path, tmp_path: Path) -> None:
        """Writes output to specified file."""
        out_file = tmp_path / "registry.json"
        rc = main([
            "--format", "json",
            "--output", str(out_file),
            "--skills-dir", str(skill_tree / ".claude" / "skills"),
            "--project-root", str(skill_tree),
        ])

        assert rc == 0
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert data["total_skills"] == 1
