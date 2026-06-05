"""CI-collected tests for the security-review form-factor skill."""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "security-review" / "SKILL.md"


def _read_skill() -> str:
    return _SKILL_MD.read_text(encoding="utf-8")


def _frontmatter(text: str) -> str:
    assert text.startswith("---\n"), "SKILL.md must start with a frontmatter fence"
    parts = text.split("---", 2)
    assert len(parts) >= 3, "SKILL.md must open with a --- frontmatter block"
    return parts[1]


def test_frontmatter_has_required_fields():
    front = _frontmatter(_read_skill())

    assert "name: security-review" in front
    assert "version:" in front
    assert "description:" in front


def test_cites_canonical_agent_template():
    text = _read_skill()

    assert "templates/agents/security.shared.md" in text
    assert "Quoted canonical contract" in text


def test_verdict_vocabulary_matches_eval_fixtures():
    text = _read_skill()

    for token in ("IDENTIFY", "OK", "ESCALATE"):
        assert token in text, f"verdict token {token!r} missing from SKILL.md"


def test_names_high_priority_cwes():
    text = _read_skill()

    for cwe in ("CWE-22", "CWE-78", "CWE-89"):
        assert cwe in text, f"{cwe} missing from the skill CWE catalog"


_EM_DASH = chr(0x2014)
_EN_DASH = chr(0x2013)


@pytest.mark.parametrize("forbidden", [_EM_DASH, _EN_DASH])
def test_no_em_or_en_dashes(forbidden: str):
    assert forbidden not in _read_skill()
