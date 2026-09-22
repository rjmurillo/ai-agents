"""Structural contract for ADR generator mandatory exit gates."""

from pathlib import Path

SKILL = Path(".claude/skills/adr-generator/SKILL.md")


def test_mandatory_exit_gates_are_ordered_and_measurable() -> None:
    text = SKILL.read_text(encoding="utf-8")

    g4 = text.index("### Phase G4: Validate")
    gates = text.index("## Mandatory Exit Gates")
    g5 = text.index("### Phase G5: Save")
    assert g4 < gates < g5

    names = (
        "Claims ledger",
        "Documentation accuracy",
        "Self-consistency",
        "Refuting seat",
        "ADR review hand-off",
    )
    positions = [text.index(name, gates, g5) for name in names]
    assert positions == sorted(positions)

    for status in ("VERIFIED", "NOT RUN", "UNAVAILABLE", "FAILED"):
        assert status in text[gates:g5]

    assert "abort condition" in text[gates:g5]
    assert "check_citation_freshness.py" in text[gates:g5]
    assert "--diff-base" in text[gates:g5]
    assert 'subagent_type="analyst"' in text[gates:g5]
    assert 'model="haiku"' in text[gates:g5]
