"""Issue #5280: adr-generator regenerates the ADR index before hand-off."""

from pathlib import Path

SKILL = Path(".claude/skills/adr-generator/SKILL.md")
COMMAND = "uv run python build/scripts/generate_adr_index.py"
GENERATOR = "build/scripts/generate_adr_index.py"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _hand_off_section(text: str) -> str:
    start = text.index("### Phase G6: Hand Off")
    return text[start : text.index("\n---", start)]


def test_hand_off_runs_the_generator_before_review() -> None:
    section = _hand_off_section(_text())

    flat = " ".join(section.split())
    assert COMMAND in section
    assert "refresh the ADR index, then hand the ADR" in flat


def test_refresh_runs_after_the_gates_that_may_edit_the_adr() -> None:
    text = _text()

    assert text.index("## Mandatory Exit Gates") < text.index(COMMAND)


def test_refresh_is_skipped_when_the_generator_is_absent() -> None:
    section = _hand_off_section(_text())

    assert f"`{GENERATOR}` does not exist" in section
    assert "skip" in section.lower()


def test_marker_names_every_path_the_refresh_prose_references() -> None:
    text = _text()
    marker_start = text.index("<!-- vendor-portability:")
    marker = text[marker_start : text.index("-->", marker_start)]

    assert GENERATOR in marker


def test_verification_checklist_covers_the_refresh() -> None:
    text = _text()
    checklist = text[text.index("## Verification") :]

    assert f"`{GENERATOR}`" in checklist
    assert "Phase G6" in checklist
