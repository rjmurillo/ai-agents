"""Structural contract for ADR generator mandatory exit gates."""

from pathlib import Path

SKILL = Path(".claude/skills/adr-generator/SKILL.md")


def test_mandatory_exit_gates_are_ordered_and_measurable() -> None:
    text = SKILL.read_text(encoding="utf-8")

    g4 = text.index("### Phase G4: Validate")
    g5 = text.index("### Phase G5: Save")
    gates = text.index("## Mandatory Exit Gates")
    g6 = text.index("### Phase G6: Hand Off")
    assert g4 < g5 < gates < g6

    names = (
        "Claims ledger",
        "Documentation accuracy",
        "Self-consistency",
        "Refuting seat",
        "ADR review hand-off",
    )
    positions = [text.index(name, gates, g6) for name in names]
    assert positions == sorted(positions)

    for status in ("VERIFIED", "NOT RUN", "UNAVAILABLE", "FAILED"):
        assert status in text[gates:g6]

    gate_text = text[gates:g6]
    assert "abort condition" in gate_text
    assert "read the cited range directly from the working tree" in gate_text
    assert "checks only citations on" in gate_text
    assert "the saved ADR as the documentation file" in gate_text
    assert "scans committed changes" in gate_text
    assert "Pass the ledger path and contents" in gate_text
    assert 'subagent_type="analyst"' in gate_text
    assert 'model="haiku"' in gate_text
