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


def test_release_bullet_routes_first_publish_through_gated_dispatch():
    """Issue 7368: the First publish runs in the gated dispatch run, not locally.

    A local publish cannot carry provenance and skips the gate. The gate sentence
    must also name the dispatch run instead of leaning on a pronoun.
    """
    section = _release_section()
    bullet = next(line for line in section.splitlines() if "only live CI publish route" in line)
    sentences = [s.strip() for s in re.split(r"(?<=\.)\s+", bullet.lstrip("- ")) if s.strip()]
    gate_sentence = next(s for s in sentences if "promotion gate" in s)
    assert "dispatch" in gate_sentence, gate_sentence
    assert not gate_sentence.startswith("It "), gate_sentence
    first_publish = next(s for s in sentences if "First publish" in s)
    assert "runs locally" not in first_publish, first_publish
    assert "dispatch" in first_publish, first_publish
    assert "NPM_TOKEN" in first_publish, first_publish


def test_releasing_md_first_publish_uses_ci_not_local():
    """Issue 7368: RELEASING.md must not tell the owner to publish from a laptop."""
    releasing = (Path(__file__).resolve().parents[3] / "RELEASING.md").read_text(encoding="utf-8")
    fenced = re.findall(r"```[a-z]*\n(.*?)```", releasing, flags=re.S)
    assert not any("npm publish" in block for block in fenced), fenced
    assert "### 3. First publish: bootstrap with a short-lived token" in releasing
    for row in (
        "Organization or user | `rjmurillo`",
        "Repository | `ai-agents`",
        "Workflow filename | `publish.yml`",
        "Environment name | `npm`",
        "Allowed actions | `npm publish`",
    ):
        assert row in releasing, row


def test_provenance_marks_release_row_reverified():
    text = _text()
    start = text.index("## Provenance and Maintenance")
    provenance = text[start:]
    assert "re-verified 2026-10-14" in provenance
