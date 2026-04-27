"""Tests for the requirements-interview SKILL.md frontmatter and structure.

These tests enforce the contract documented in:
- .claude/rules/claude-agents.md (required frontmatter fields)
- scripts/validation/skill_frontmatter.py (allowed model identifiers, name regex)
- scripts/validation/skill_size.py (500 line cap)

The skill is prompt-only (no Python scripts). The contract test guards against
silent regressions in frontmatter or required sections that the /spec command
relies on.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

try:  # python-frontmatter is in the dev deps
    import frontmatter
    HAS_FRONTMATTER = True
except ImportError:  # pragma: no cover
    HAS_FRONTMATTER = False

SKILL_PATH = (
    Path(__file__).resolve().parent.parent / "SKILL.md"
)

NAME_PATTERN = re.compile(r"^[a-z0-9-]{1,64}$")
VALID_MODELS = {
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-sonnet-4-0",
    "opus",
    "sonnet",
    "haiku",
}
SKILL_LINE_LIMIT = 500
DESCRIPTION_MAX = 1024
REQUIRED_SECTIONS = {
    "## Triggers",
    "## Inputs",
    "## Outputs",
    "## Method",
    "## Question Discipline",
    "## Branch Checklist",
    "## Anti-Patterns",
    "## Quality Gates",
    "## Structured Output",
    "## Handoff",
    "## References",
}


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skill_post(skill_text):
    if not HAS_FRONTMATTER:
        pytest.skip("python-frontmatter not installed")
    return frontmatter.loads(skill_text)


def test_skill_file_exists():
    assert SKILL_PATH.is_file(), f"SKILL.md missing at {SKILL_PATH}"


def test_skill_within_size_limit(skill_text):
    line_count = len(skill_text.splitlines())
    assert line_count <= SKILL_LINE_LIMIT, (
        f"SKILL.md is {line_count} lines, exceeds {SKILL_LINE_LIMIT}"
    )


def test_frontmatter_required_fields(skill_post):
    for field in ("name", "description", "version", "model"):
        assert field in skill_post.metadata, f"missing frontmatter field: {field}"


def test_name_matches_pattern(skill_post):
    name = skill_post.metadata["name"]
    assert name == "requirements-interview"
    assert NAME_PATTERN.match(name), f"name {name!r} fails {NAME_PATTERN.pattern}"


def test_description_constraints(skill_post):
    desc = skill_post.metadata["description"]
    assert isinstance(desc, str) and desc.strip(), "description must be non-empty"
    assert len(desc) <= DESCRIPTION_MAX, (
        f"description is {len(desc)} chars, exceeds {DESCRIPTION_MAX}"
    )
    assert "<" not in desc and ">" not in desc, "description must not contain XML tags"


def test_model_is_supported(skill_post):
    model = skill_post.metadata["model"]
    assert model in VALID_MODELS, (
        f"model {model!r} not in supported list (see scripts/validation/skill_frontmatter.py)"
    )


def test_required_sections_present(skill_text):
    missing = sorted(s for s in REQUIRED_SECTIONS if s not in skill_text)
    assert not missing, f"SKILL.md missing required sections: {missing}"


def test_grill_me_pattern_referenced(skill_text):
    assert "grill-me" in skill_text.lower(), (
        "SKILL.md must reference the grill-me pattern (issue #1798 acceptance criterion)"
    )
    assert "design tree" in skill_text.lower(), (
        "SKILL.md must reference design tree traversal"
    )


def test_recommended_answer_discipline(skill_text):
    assert "recommended answer" in skill_text.lower(), (
        "Question discipline must require a recommended answer per question"
    )


def test_codebase_first_principle(skill_text):
    assert "codebase" in skill_text.lower() and (
        "grep" in skill_text.lower() or "explore" in skill_text.lower()
    ), "SKILL.md must instruct grepping the codebase before asking the user"
