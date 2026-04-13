"""Tests for skill_registry module.

Verifies skill scanning, frontmatter parsing, categorization, and output
formatting for the skill utilization tracking system.

See: Issue #1266 - Implement skill utilization tracking
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.skill_registry import (
    SkillMetadata,
    build_registry,
    categorize_skill,
    filter_stale,
    format_json,
    format_markdown,
    format_session_message,
    main,
    parse_frontmatter,
    scan_skill,
)


@pytest.fixture
def skill_tree(tmp_path: Path) -> Path:
    """Create a mock .claude/skills/ directory with two skills."""
    skills_dir = tmp_path / ".claude" / "skills"

    # Skill with full frontmatter
    alpha = skills_dir / "alpha-skill"
    alpha.mkdir(parents=True)
    (alpha / "SKILL.md").write_text(
        "---\n"
        "name: alpha-skill\n"
        "version: 1.0.0\n"
        "model: claude-sonnet-4-5\n"
        "description: Analyzes code quality metrics\n"
        "---\n\n# Alpha\n"
    )
    tests_dir = alpha / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_alpha.py").touch()

    # Skill with minimal frontmatter
    beta = skills_dir / "beta-tool"
    beta.mkdir(parents=True)
    (beta / "SKILL.md").write_text(
        "---\nname: beta-tool\ndescription: Security scanning tool\n---\n\n# Beta\n"
    )

    # Skill with no SKILL.md
    gamma = skills_dir / "gamma"
    gamma.mkdir(parents=True)
    (gamma / "README.md").write_text("# Gamma\n")

    return skills_dir


class TestParseFrontmatter:
    """Tests for parse_frontmatter function."""

    def test_extracts_fields(self, tmp_path: Path) -> None:
        """Extracts key-value pairs from YAML frontmatter."""
        md = tmp_path / "SKILL.md"
        md.write_text("---\nname: test\ndescription: A test skill\n---\n# Body\n")
        result = parse_frontmatter(md)
        assert result["name"] == "test"
        assert result["description"] == "A test skill"

    def test_returns_empty_when_no_frontmatter(self, tmp_path: Path) -> None:
        """Returns empty dict when file has no frontmatter delimiters."""
        md = tmp_path / "SKILL.md"
        md.write_text("# No frontmatter\n")
        result = parse_frontmatter(md)
        assert result == {}

    def test_returns_empty_for_empty_file(self, tmp_path: Path) -> None:
        """Returns empty dict for empty file."""
        md = tmp_path / "SKILL.md"
        md.write_text("")
        result = parse_frontmatter(md)
        assert result == {}

    def test_ignores_list_items(self, tmp_path: Path) -> None:
        """Skips YAML list items (lines starting with -)."""
        md = tmp_path / "SKILL.md"
        md.write_text("---\nname: test\nallowed-tools:\n  - Read\n  - Grep\n---\n")
        result = parse_frontmatter(md)
        assert result["name"] == "test"
        assert "Read" not in result.values()


class TestCategorizeSkill:
    """Tests for categorize_skill function."""

    def test_security_category(self) -> None:
        """Assigns security category for security keywords."""
        assert categorize_skill("codeql-scan", "scan for vulnerabilities") == "security"

    def test_memory_category(self) -> None:
        """Assigns memory category for memory keywords."""
        assert categorize_skill("curating-memories", "manage memory") == "memory"

    def test_analysis_category(self) -> None:
        """Assigns analysis category for analysis keywords."""
        assert categorize_skill("code-review", "analyze code quality") == "analysis"

    def test_defaults_to_other(self) -> None:
        """Falls back to other when no keywords match."""
        assert categorize_skill("xyzzy", "does unknown things") == "other"


class TestScanSkill:
    """Tests for scan_skill function."""

    def test_extracts_metadata(self, skill_tree: Path) -> None:
        """Extracts name, description, model from frontmatter."""
        skill_dir = skill_tree / "alpha-skill"
        result = scan_skill(skill_dir, skill_tree.parent.parent)
        assert result.name == "alpha-skill"
        assert result.model == "claude-sonnet-4-5"
        assert result.has_tests is True

    def test_handles_missing_skill_md(self, skill_tree: Path) -> None:
        """Uses directory name when SKILL.md is absent."""
        skill_dir = skill_tree / "gamma"
        result = scan_skill(skill_dir, skill_tree.parent.parent)
        assert result.name == "gamma"
        assert result.description == ""
        assert result.model == ""

    def test_detects_no_tests(self, skill_tree: Path) -> None:
        """Reports has_tests=False when no tests directory exists."""
        skill_dir = skill_tree / "beta-tool"
        result = scan_skill(skill_dir, skill_tree.parent.parent)
        assert result.has_tests is False


class TestBuildRegistry:
    """Tests for build_registry function."""

    def test_finds_all_skills(self, skill_tree: Path) -> None:
        """Discovers all skill directories."""
        result = build_registry(skill_tree, skill_tree.parent.parent)
        names = [s.name for s in result]
        assert "alpha-skill" in names
        assert "beta-tool" in names
        assert "gamma" in names

    def test_sorted_by_name(self, skill_tree: Path) -> None:
        """Returns skills sorted alphabetically by name."""
        result = build_registry(skill_tree, skill_tree.parent.parent)
        names = [s.name for s in result]
        assert names == sorted(names)

    def test_skips_hidden_dirs(self, skill_tree: Path) -> None:
        """Ignores directories starting with dot."""
        (skill_tree / ".hidden").mkdir()
        result = build_registry(skill_tree, skill_tree.parent.parent)
        names = [s.name for s in result]
        assert ".hidden" not in names


class TestFilterStale:
    """Tests for filter_stale function."""

    def test_filters_old_skills(self) -> None:
        """Returns only skills older than threshold."""
        skills = [
            SkillMetadata("old", "p", "d", "c", "2020-01-01", "", False, False, 1),
            SkillMetadata("new", "p", "d", "c", "2099-01-01", "", False, False, 1),
        ]
        result = filter_stale(skills, stale_days=30)
        assert len(result) == 1
        assert result[0].name == "old"

    def test_excludes_unknown_dates(self) -> None:
        """Excludes skills with unknown last_modified."""
        skills = [
            SkillMetadata("unk", "p", "d", "c", "unknown", "", False, False, 1),
        ]
        result = filter_stale(skills, stale_days=30)
        assert len(result) == 0


class TestFormatJson:
    """Tests for format_json function."""

    def test_produces_valid_json(self) -> None:
        """Output is valid JSON with expected structure."""
        import json

        skills = [
            SkillMetadata("test", "p", "desc", "cat", "2026-01-01", "sonnet", True, False, 2),
        ]
        output = format_json(skills)
        data = json.loads(output)
        assert "generated" in data
        assert "skills" in data
        assert len(data["skills"]) == 1
        assert data["skills"][0]["name"] == "test"


class TestFormatMarkdown:
    """Tests for format_markdown function."""

    def test_contains_table_header(self) -> None:
        """Output contains markdown table header."""
        skills = [
            SkillMetadata("test", "p", "desc", "cat", "2026-01-01", "sonnet", True, False, 2),
        ]
        output = format_markdown(skills)
        assert "| Name |" in output
        assert "| test |" in output

    def test_contains_category_summary(self) -> None:
        """Output includes category breakdown."""
        skills = [
            SkillMetadata("a", "p", "d", "security", "2026-01-01", "", False, False, 1),
            SkillMetadata("b", "p", "d", "security", "2026-01-01", "", False, False, 1),
        ]
        output = format_markdown(skills)
        assert "**security**: 2 skills" in output


class TestMain:
    """Tests for main entry point."""

    def test_json_output(self, skill_tree: Path) -> None:
        """Main produces JSON output with --format json."""
        exit_code = main(
            [
                "--format",
                "json",
                "--skills-dir",
                str(skill_tree),
                "--project-root",
                str(skill_tree.parent.parent),
            ]
        )
        assert exit_code == 0

    def test_markdown_output(self, skill_tree: Path) -> None:
        """Main produces markdown output with --format markdown."""
        exit_code = main(
            [
                "--format",
                "markdown",
                "--skills-dir",
                str(skill_tree),
                "--project-root",
                str(skill_tree.parent.parent),
            ]
        )
        assert exit_code == 0

    def test_missing_skills_dir(self, tmp_path: Path) -> None:
        """Returns error code when skills directory does not exist."""
        exit_code = main(
            [
                "--skills-dir",
                str(tmp_path / "nonexistent"),
                "--project-root",
                str(tmp_path),
            ]
        )
        assert exit_code == 2

    def test_show_stale(self, skill_tree: Path) -> None:
        """--show-stale flag filters results."""
        exit_code = main(
            [
                "--show-stale",
                "--stale-days",
                "30",
                "--skills-dir",
                str(skill_tree),
                "--project-root",
                str(skill_tree.parent.parent),
            ]
        )
        assert exit_code == 0

    def test_session_message(self, skill_tree: Path) -> None:
        """--session-message outputs session-ready stale skill notification."""
        exit_code = main(
            [
                "--session-message",
                "--stale-days",
                "30",
                "--skills-dir",
                str(skill_tree),
                "--project-root",
                str(skill_tree.parent.parent),
            ]
        )
        assert exit_code == 0


class TestFormatSessionMessage:
    """Tests for format_session_message function."""

    def test_returns_empty_when_no_stale(self) -> None:
        """Returns empty string when no skills are stale."""
        assert format_session_message([], stale_days=30) == ""

    def test_lists_stale_skill_names(self) -> None:
        """Message includes stale skill names."""
        skills = [
            SkillMetadata("old-skill", "p", "d", "c", "2020-01-01", "", False, False, 1),
        ]
        msg = format_session_message(skills, stale_days=30)
        assert "old-skill" in msg
        assert "30+ days" in msg

    def test_truncates_at_ten_skills(self) -> None:
        """Truncates to first 10 skills with overflow count."""
        skills = [
            SkillMetadata(f"skill-{i}", "p", "d", "c", "2020-01-01", "", False, False, 1)
            for i in range(15)
        ]
        msg = format_session_message(skills, stale_days=30)
        assert "and 5 more" in msg


class TestPathTraversal:
    """Tests for CWE-22 path traversal prevention."""

    def test_rejects_skills_dir_outside_project_root(self, tmp_path: Path) -> None:
        """Returns error code when skills dir escapes project root."""
        outside = tmp_path / "outside"
        outside.mkdir()
        project = tmp_path / "project"
        project.mkdir()
        exit_code = main([
            "--project-root", str(project),
            "--skills-dir", str(outside),
        ])
        assert exit_code == 2

    def test_rejects_skills_dir_traversal(self, tmp_path: Path) -> None:
        """Returns error code when skills dir uses .. to escape project root."""
        project = tmp_path / "project"
        project.mkdir()
        exit_code = main([
            "--project-root", str(project),
            "--skills-dir", str(project / ".." / "escape"),
        ])
        assert exit_code == 2
