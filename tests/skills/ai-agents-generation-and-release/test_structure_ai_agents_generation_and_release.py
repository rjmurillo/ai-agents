"""Structure test for this skill, mirroring the prose-self-check tests pattern."""

import re
from pathlib import Path

SKILL_DIR = (
    Path(__file__).resolve().parents[3] / ".claude" / "skills" / "ai-agents-generation-and-release"
)
SKILL_MD = SKILL_DIR / "SKILL.md"


def _text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def test_skill_md_exists():
    assert SKILL_MD.is_file()


def test_frontmatter_required_fields():
    text = _text()
    assert text.startswith("---\n")
    fm = text.split("---", 2)[1]
    assert re.search(r"^name: ai-agents-generation-and-release$", fm, re.M)
    assert re.search(r"^version: ", fm, re.M)
    assert re.search(r"^description: ", fm, re.M)


def test_body_structure():
    text = _text()
    assert re.search(r"^# ", text, re.M), "H1 title required"
    assert "## Triggers" in text
    assert re.search(r"^## Process|^### Phase \d", text, re.M)
    assert len(re.findall(r"- \[ \]", text)) >= 2, "verification checkboxes required"
    assert "## Provenance" in text


def test_no_em_or_en_dashes():
    for ch in ("\u2014", "\u2013"):
        assert ch not in _text()


def test_size_cap():
    assert len(_text().splitlines()) <= 500


def _release_section() -> str:
    text = _text()
    start = text.index("### Phase 5: npm Release Path")
    end = text.index("\n## ", start)
    return text[start:end]


def test_release_path_does_not_recommend_tag_push_publish():
    """Issue 6590: publish.yml refuses the v* tag route; the skill must not route readers there."""
    text = _text()
    for stale in ("--tags", "git tag v", "fires on `v*` tags", "retag"):
        assert stale not in text, f"stale tag-publish guidance: {stale!r}"


def test_release_path_routes_to_releasing_md_and_dispatch():
    section = _release_section()
    assert "RELEASING.md" in section
    assert "workflow_dispatch" in section
    assert "dormant" in section
    assert "ai-agents-change-control" in section


def test_release_path_drops_closed_issue_cites():
    """PR 6620 review: #3865 and #5636 are closed; the skill must not say they track work."""
    section = _release_section()
    assert "#3865" not in section
    assert "#5636" not in section
    assert "ADR-113 Resolved Question 2" in section


def test_release_path_scopes_dispatch_to_ci_and_names_first_publish():
    """RELEASING.md keeps a one-time local first publish, so dispatch is the only live CI route."""
    section = _release_section()
    assert "only live CI publish route" in section
    assert "First publish" in section


def test_promotion_gate_sentence_names_dispatch_not_first_publish():
    """The gate sentence must not read as if the local First publish is gated.

    RELEASING.md runs the First publish as a plain local `npm publish`, with no
    promotion gate. A pronoun after the First publish sentence would bind to it.
    """
    section = _release_section()
    bullet = next(line for line in section.splitlines() if "only live CI publish route" in line)
    sentences = [s.strip() for s in re.split(r"(?<=\.)\s+", bullet.lstrip("- ")) if s.strip()]
    gate_index = next(
        i for i, s in enumerate(sentences) if "promotion gate" in s and "runs no" not in s
    )
    gate_sentence = sentences[gate_index]
    assert "dispatch" in gate_sentence, gate_sentence
    assert not gate_sentence.startswith("It "), gate_sentence
    assert "First publish" not in sentences[gate_index - 1], sentences[gate_index - 1]
    first_publish = next(s for s in sentences if "First publish" in s)
    assert "no promotion gate" in first_publish, first_publish


def test_provenance_marks_release_row_reverified():
    text = _text()
    start = text.index("## Provenance and Maintenance")
    provenance = text[start:]
    assert "re-verified 2026-10-14 for issue #6590" in provenance
