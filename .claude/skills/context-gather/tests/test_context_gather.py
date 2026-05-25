"""Smoke tests for context-gather skill SKILL.md structure and frontmatter."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"


@pytest.fixture(scope="session")
def skill_content() -> str:
    """Read SKILL.md content once per test session."""
    assert SKILL_MD.exists(), f"SKILL.md not found at {SKILL_MD}"
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
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
        # Precondition: section header must exist before splitting, so the
        # test fails cleanly with a useful message instead of IndexError if
        # the section is renamed or removed. Tests do not assume execution
        # order, so this assert cannot rely on test_anti_patterns_table_exists.
        assert "## Anti-Patterns" in skill_content, (
            "SKILL.md missing '## Anti-Patterns' section (required before counting rows)"
        )
        anti_pattern_section = skill_content.split("## Anti-Patterns")[1]
        next_section = anti_pattern_section.find("\n## ")
        if next_section != -1:
            anti_pattern_section = anti_pattern_section[:next_section]
        # Markdown tables count the header row AND the |---|---| separator
        # row as ``\n|`` occurrences; subtract both to get data-row count.
        row_count = anti_pattern_section.count("\n|") - 2
        assert row_count >= 3, f"Anti-Patterns table has {row_count} entries, need at least 3"

    def test_verification_section_exists(self, skill_content: str) -> None:
        assert "## Verification" in skill_content, "SKILL.md missing '## Verification' section"

    def test_verification_has_minimum_items(self, skill_content: str) -> None:
        # Precondition: section header must exist before splitting, so the
        # test fails cleanly with a useful message instead of IndexError if
        # the section is renamed or removed. Tests do not assume execution
        # order, so this assert cannot rely on test_verification_section_exists.
        assert "## Verification" in skill_content, (
            "SKILL.md missing '## Verification' section (required before counting items)"
        )
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

    def test_context_retrieval_subagent_exists(self) -> None:
        """SKILL.md delegates to the context-retrieval subagent; verify the
        subagent file exists so renaming/deleting it is caught immediately."""
        repo_root = SKILL_DIR.parents[2]
        subagent = repo_root / ".claude" / "agents" / "context-retrieval.md"
        assert subagent.exists(), (
            f"SKILL.md delegates to context-retrieval subagent but {subagent} is missing"
        )

    def test_trigger_phrase_count_in_range(self, skill_content: str) -> None:
        """`.claude/skills/CLAUDE.md` mandates 3-5 trigger phrases per skill."""
        triggers_section = skill_content.split("## Triggers")[1]
        next_section = triggers_section.find("\n## ")
        if next_section != -1:
            triggers_section = triggers_section[:next_section]
        backtick_phrases = re.findall(r"`([^`]+)`", triggers_section)
        count = len(backtick_phrases)
        assert 3 <= count <= 5, (
            f"Triggers section has {count} backtick-wrapped phrases; "
            f"`.claude/skills/CLAUDE.md` requires 3-5"
        )

    def test_triggers_backtick_wrapped(self, skill_content: str) -> None:
        """Trigger phrases must be backtick-wrapped, not quote-wrapped."""
        triggers_section = skill_content.split("## Triggers")[1]
        next_section = triggers_section.find("\n## ")
        if next_section != -1:
            triggers_section = triggers_section[:next_section]
        # Look for the table body rows; each leading column must contain backticks
        table_rows = [
            line for line in triggers_section.splitlines()
            if line.startswith("|") and "---" not in line and "Phrase" not in line
        ]
        for row in table_rows:
            first_col = row.split("|")[1] if len(row.split("|")) > 1 else ""
            if first_col.strip():
                assert "`" in first_col, (
                    f"Trigger row first column missing backticks: {row.strip()}"
                )
