"""Tests for scripts/validate_skill_installation.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validate_skill_installation import (
    main,
    parse_frontmatter,
    validate_skill_dir,
)


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    """Create a valid skill directory."""
    skill = tmp_path / "test-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: A test skill\nversion: 1.0.0\n---\n\n# Test Skill\n"
    )
    return skill


@pytest.fixture
def repo_root(tmp_path: Path, skill_dir: Path) -> Path:
    """Create a repo root with .claude/skills/ structure."""
    claude_skills = tmp_path / ".claude" / "skills"
    claude_skills.mkdir(parents=True)
    # Move skill_dir content into the proper location
    target = claude_skills / "test-skill"
    target.mkdir()
    (target / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: A test skill\nversion: 1.0.0\n---\n\n# Test\n"
    )
    return tmp_path


class TestParseFrontmatter:
    def test_valid_frontmatter(self, skill_dir: Path) -> None:
        result = parse_frontmatter(skill_dir / "SKILL.md")
        assert result is not None
        assert result["name"] == "test-skill"
        assert result["description"] == "A test skill"

    def test_missing_frontmatter(self, tmp_path: Path) -> None:
        md = tmp_path / "no-frontmatter.md"
        md.write_text("# No Frontmatter\n")
        assert parse_frontmatter(md) is None

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        md = tmp_path / "bad.md"
        md.write_text("---\ninvalid: [unclosed\n---\n")
        assert parse_frontmatter(md) is None

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        assert parse_frontmatter(tmp_path / "missing.md") is None


class TestValidateSkillDir:
    def test_valid_skill(self, skill_dir: Path) -> None:
        errors = validate_skill_dir(skill_dir)
        assert errors == []

    def test_missing_skill_md(self, tmp_path: Path) -> None:
        skill = tmp_path / "empty-skill"
        skill.mkdir()
        errors = validate_skill_dir(skill)
        assert len(errors) == 1
        assert "missing SKILL.md" in errors[0]

    def test_missing_required_fields(self, tmp_path: Path) -> None:
        skill = tmp_path / "bad-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nversion: 1.0.0\n---\n")
        errors = validate_skill_dir(skill)
        assert any("missing required field 'name'" in e for e in errors)
        assert any("missing required field 'description'" in e for e in errors)

    def test_name_mismatch(self, tmp_path: Path) -> None:
        skill = tmp_path / "my-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: other-skill\ndescription: Test\n---\n")
        errors = validate_skill_dir(skill)
        assert any("does not match directory name" in e for e in errors)

    def test_name_case_insensitive(self, tmp_path: Path) -> None:
        skill = tmp_path / "MySkill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: myskill\ndescription: Test\n---\n")
        errors = validate_skill_dir(skill)
        assert errors == []


class TestMain:
    def test_valid_repo(self, repo_root: Path) -> None:
        result = main(["--source", str(repo_root)])
        assert result == 0

    def test_missing_skills_dir(self, tmp_path: Path) -> None:
        result = main(["--source", str(tmp_path)])
        assert result == 2

    def test_verbose_flag(self, repo_root: Path) -> None:
        result = main(["--source", str(repo_root), "--verbose"])
        assert result == 0
