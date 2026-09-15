"""Structure test for this skill, mirroring the prose-self-check tests pattern."""
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_MD = SKILL_DIR / "SKILL.md"


def _text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def test_skill_md_exists():
    assert SKILL_MD.is_file()


def test_frontmatter_required_fields():
    text = _text()
    assert text.startswith("---\n")
    fm = text.split("---", 2)[1]
    assert re.search(r"^name: ai-agents-docs-of-record$", fm, re.M)
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


def _provenance_rows() -> list[str]:
    """Data rows of the Fact / Source / Re-verify table."""
    rows: list[str] = []
    in_table = False
    for line in _text().splitlines():
        if line.startswith("| Fact | Source | Re-verify |"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            if line.startswith("|---"):
                continue
            rows.append(line)
    return rows


def test_provenance_table_is_populated():
    assert len(_provenance_rows()) >= 15


def test_branch_pattern_reverify_anchors_on_the_definition():
    """Regression guard for the PR #4025 review finding.

    A bare ``grep -n "BRANCH_PATTERN"`` exits 0 when the symbol survives only in
    a comment or a call site, so the row passed without proving the constant it
    names as the source still exists. Deleting the assignment left the command
    green. The command must anchor to the assignment itself.
    """
    row = next(r for r in _provenance_rows() if r.startswith("| Branch naming pattern |"))
    assert '"^BRANCH_PATTERN = re.compile"' in row, (
        "re-verify command must anchor to the constant assignment, not a bare symbol mention"
    )


def test_provenance_table_has_no_escaped_pipes():
    """An escaped pipe is valid Markdown but reaches a raw reader intact.

    In the row that carried one, the escape let a second shell statement mask
    the first statement's failure.
    """
    for row in _provenance_rows():
        assert "\\|" not in row, f"escaped pipe in provenance row: {row[:60]}"

