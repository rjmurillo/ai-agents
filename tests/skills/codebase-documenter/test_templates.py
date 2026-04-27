#!/usr/bin/env python3
"""Tests for the codebase-documenter skill (issue #1803).

Validates SKILL.md frontmatter, file existence, fence balance, the absence of
forbidden personal-workspace strings, and unicode safety. The tests parse the
files for real; they do not merely assert paths exist.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = REPO_ROOT / ".claude" / "skills" / "codebase-documenter"
TEMPLATES_DIR = SKILL_ROOT / "assets" / "templates"
REFERENCES_DIR = SKILL_ROOT / "references"

TEMPLATE_FILES = [
    TEMPLATES_DIR / "README.template.md",
    TEMPLATES_DIR / "ARCHITECTURE.template.md",
    TEMPLATES_DIR / "API.template.md",
    TEMPLATES_DIR / "CODE_COMMENTS.template.md",
]

REFERENCE_FILES = [
    REFERENCES_DIR / "documentation_guidelines.md",
    REFERENCES_DIR / "visual_aids_guide.md",
]

ALL_SKILL_FILES = [SKILL_ROOT / "SKILL.md"] + TEMPLATE_FILES + REFERENCE_FILES

VALID_DESCRIPTION_VERBS = {
    "Generate",
    "Create",
    "Produce",
    "Scaffold",
    "Build",
    "Write",
}

FORBIDDEN_SUBSTRINGS = ["/home/", "Richard", "Microsoft", "openclaw"]


def _read_skill_md_frontmatter() -> dict:
    """Parse the YAML frontmatter at the top of SKILL.md."""
    content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise AssertionError("SKILL.md must start with '---' frontmatter delimiter")
    _, fm, _ = content.split("---\n", 2)
    return yaml.safe_load(fm)


class TestSkillFrontmatter:
    """Frontmatter rules from .agents/steering/claude-skills.md."""

    def test_skill_md_frontmatter_valid(self) -> None:
        fm = _read_skill_md_frontmatter()
        assert fm["name"] == "codebase-documenter"
        assert "version" in fm and isinstance(fm["version"], str)
        description = fm["description"]
        assert isinstance(description, str)
        assert description, "description must be non-empty"
        assert len(description) <= 200, (
            f"description must be <= 200 chars, got {len(description)}"
        )
        first_word = description.split()[0]
        assert first_word in VALID_DESCRIPTION_VERBS, (
            f"description must start with an action verb; got '{first_word}'"
        )
        assert fm.get("license") == "MIT"

    def test_model_is_set(self) -> None:
        fm = _read_skill_md_frontmatter()
        assert "model" in fm
        assert fm["model"], "model must be non-empty"


class TestStructure:
    """Skill directory layout."""

    def test_skill_directory_structure(self) -> None:
        assert SKILL_ROOT.is_dir()
        assert (SKILL_ROOT / "SKILL.md").is_file()
        assert TEMPLATES_DIR.is_dir()
        assert REFERENCES_DIR.is_dir()

    def test_all_templates_exist(self) -> None:
        for path in TEMPLATE_FILES:
            assert path.is_file(), f"missing template: {path}"

    def test_all_references_exist(self) -> None:
        for path in REFERENCE_FILES:
            assert path.is_file(), f"missing reference: {path}"


class TestContent:
    """Content-level invariants."""

    @pytest.mark.parametrize("path", TEMPLATE_FILES)
    def test_templates_have_balanced_code_fences(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        fences = re.findall(r"^```", text, flags=re.MULTILINE)
        assert len(fences) % 2 == 0, (
            f"unbalanced code fences in {path.name}: {len(fences)} fence lines"
        )

    @pytest.mark.parametrize("path", ALL_SKILL_FILES)
    def test_no_forbidden_strings_in_skill_files(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN_SUBSTRINGS:
            assert needle not in text, (
                f"{path.name} contains forbidden substring: {needle!r}"
            )

    @pytest.mark.parametrize("path", TEMPLATE_FILES)
    def test_templates_have_unicode_safe_content(self, path: Path) -> None:
        # Reading as utf-8 with strict errors raises if anything is wrong.
        path.read_text(encoding="utf-8", errors="strict")
