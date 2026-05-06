"""Smoke tests for context-gather skill SKILL.md structure and frontmatter."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"


@pytest.fixture
def skill_content() -> str:
    """Read SKILL.md content once per test session."""
    assert SKILL_MD.exists(), f"SKILL.md not found at {SKILL_MD}"
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.fixture
def frontmatter(skill_content: str) -> dict[str, str]:
    """Extract YAML frontmatter as a flat dict of string values."""
    lines = skill_content.splitlines()
    assert lines[0].strip() == "---", "SKILL.md must start with '---' frontmatter delimiter"

    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break

    assert end_idx is not None, "SKILL.md missing closing '---' frontmatter delimiter"

    fm: dict[str, str] = {}
    for line in lines[1:end_idx]:
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    return fm


class TestFrontmatter:
    """Verify required frontmatter fields exist and have correct values."""

    def test_name_field_present(self, frontmatter: dict[str, str]) -> None:
        assert "name" in frontmatter, "Frontmatter missing required 'name' field"

    def test_name_value(self, frontmatter: dict[str, str]) -> None:
        assert frontmatter["name"] == "context-gather"

    def test_description_field_present(self, frontmatter: dict[str, str]) -> None:
        assert "description" in frontmatter, "Frontmatter missing required 'description' field"

    def test_description_not_empty(self, frontmatter: dict[str, str]) -> None:
        assert len(frontmatter["description"]) > 0, "Description must not be empty"

    def test_model_field_present(self, frontmatter: dict[str, str]) -> None:
        assert "model" in frontmatter, "Frontmatter missing 'model' field"

    def test_model_value(self, frontmatter: dict[str, str]) -> None:
        assert frontmatter["model"] == "claude-sonnet-4-6"

    def test_version_field_present(self, frontmatter: dict[str, str]) -> None:
        assert "version" in frontmatter, "Frontmatter missing 'version' field"

    def test_version_semver(self, frontmatter: dict[str, str]) -> None:
        assert re.match(
            r"^\d+\.\d+\.\d+$", frontmatter["version"]
        ), f"Version '{frontmatter['version']}' is not valid semver"


class TestStructure:
    """Verify SKILL.md has required structural sections."""

    def test_triggers_table_exists(self, skill_content: str) -> None:
        assert "## Triggers" in skill_content, "SKILL.md missing '## Triggers' section"
        assert "| Phrase |" in skill_content or "| Trigger" in skill_content, (
            "Triggers section missing table header"
        )

    def test_process_section_exists(self, skill_content: str) -> None:
        assert "## Process" in skill_content or "### Phase" in skill_content, (
            "SKILL.md missing '## Process' or '### Phase' section"
        )

    def test_anti_patterns_table_exists(self, skill_content: str) -> None:
        assert "## Anti-Patterns" in skill_content, "SKILL.md missing '## Anti-Patterns' section"

    def test_anti_patterns_has_minimum_entries(self, skill_content: str) -> None:
        anti_pattern_section = skill_content.split("## Anti-Patterns")[1]
        next_section = anti_pattern_section.find("\n## ")
        if next_section != -1:
            anti_pattern_section = anti_pattern_section[:next_section]
        row_count = anti_pattern_section.count("\n|") - 1  # subtract header row
        assert row_count >= 3, f"Anti-Patterns table has {row_count} entries, need at least 3"

    def test_verification_section_exists(self, skill_content: str) -> None:
        assert "## Verification" in skill_content, "SKILL.md missing '## Verification' section"

    def test_verification_has_minimum_items(self, skill_content: str) -> None:
        verification_section = skill_content.split("## Verification")[1]
        next_section = verification_section.find("\n## ")
        if next_section != -1:
            verification_section = verification_section[:next_section]
        checkbox_count = verification_section.count("- [ ]")
        assert checkbox_count >= 4, (
            f"Verification checklist has {checkbox_count} items, need at least 4"
        )

    def test_references_section_exists(self, skill_content: str) -> None:
        assert "## References" in skill_content, "SKILL.md missing '## References' section"

    def test_context_loaded_marker_documented(self, skill_content: str) -> None:
        assert "CONTEXT_LOADED:" in skill_content, (
            "SKILL.md must document the CONTEXT_LOADED marker"
        )

    def test_spec_005_referenced(self, skill_content: str) -> None:
        assert "SPEC-005" in skill_content, "SKILL.md must reference SPEC-005"
