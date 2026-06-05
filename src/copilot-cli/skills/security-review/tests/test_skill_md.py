"""Tests for the security-review SKILL.md (Issue #1875).

The skill is the `skill` form-factor counterpart to the security agent: it
carries the security-review knowledge as parent-inline content. These tests
pin the contract the eval harness and the canonical-source-mirror rule depend
on: valid frontmatter, a citation back to the canonical agent template, and the
verdict vocabulary the eval fixtures score against.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = Path(__file__).resolve().parent.parent / "SKILL.md"


def _read_skill() -> str:
    return _SKILL_MD.read_text(encoding="utf-8")


def _frontmatter(text: str) -> str:
    assert text.startswith("---\n"), "SKILL.md must start with a frontmatter fence"
    parts = text.split("---", 2)
    assert len(parts) >= 3, "SKILL.md must open with a --- frontmatter block"
    return parts[1]


def test_skill_md_exists():
    assert _SKILL_MD.is_file()


def test_frontmatter_has_required_fields():
    # Arrange
    front = _frontmatter(_read_skill())
    # Assert: claude-skills.md requires name, version, description.
    assert "name: security-review" in front
    assert "version:" in front
    assert "description:" in front


def test_cites_canonical_agent_template():
    # The canonical-source-mirror rule requires the mirror to cite its source.
    text = _read_skill()
    assert "templates/agents/security.shared.md" in text


def test_verdict_vocabulary_matches_eval_fixtures():
    # The eval fixtures score verdicts IDENTIFY / OK / ESCALATE. The skill
    # content must teach the same vocabulary so the skill variant is scored on
    # the same axis as the agent variant.
    text = _read_skill()
    for token in ("IDENTIFY", "OK", "ESCALATE"):
        assert token in text, f"verdict token {token!r} missing from SKILL.md"


def test_names_high_priority_cwes():
    # The form-factor comparison holds content constant; the skill must carry
    # the CWE catalog the agent carries, not a stub.
    text = _read_skill()
    for cwe in ("CWE-22", "CWE-78", "CWE-89"):
        assert cwe in text, f"{cwe} missing from the skill CWE catalog"


# Reference the prohibited dashes by codepoint, not as literal bytes, so this
# test file itself does not trip the dash validator (the tests/hooks/fixtures/
# carve-out does not extend to skill test dirs). U+2014 em dash, U+2013 en dash.
_EM_DASH = chr(0x2014)
_EN_DASH = chr(0x2013)


def test_no_em_or_en_dashes():
    # universal.md: no U+2014 / U+2013 in authored text.
    text = _read_skill()
    assert _EM_DASH not in text
    assert _EN_DASH not in text


@pytest.mark.parametrize("forbidden", [_EM_DASH, _EN_DASH])
def test_dash_prohibition_parametrized(forbidden: str):
    assert forbidden not in _read_skill()
