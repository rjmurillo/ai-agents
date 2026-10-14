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
