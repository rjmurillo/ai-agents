"""Verify canonical template and generated entry points remain synchronized."""

import ast
from pathlib import Path

from tests.skills._template_contract import assert_template_owned_contract

REPO = Path(__file__).resolve().parents[3]


def test_skill_doctor_template_contract() -> None:
    assert_template_owned_contract("skill-doctor")


def test_template_routes_adr_drift_to_its_step() -> None:
    """The ADR drift trigger, intent, fast path, and Step 1a all ship in the template."""
    text = (REPO / "templates/skills/skill-doctor.SKILL.md.tmpl").read_text(encoding="utf-8")
    frontmatter, body = text.split("\n---\n", 1)

    assert "`check ADR drift`" in frontmatter.split("description:", 1)[1].splitlines()[0]
    assert "      - check ADR drift" in frontmatter
    assert "- `check ADR drift`" in body.split("## Triggers", 1)[1].split("\n## ", 1)[0]
    assert "#### ADR-only fast path" in body
    assert "### Step 1a: ADR drift" in body
    assert "adr_drift.py" in body.split("## Scripts", 1)[1].split("\n## ", 1)[0]


def test_known_adr_folders_cover_the_adr_review_folders() -> None:
    """adr-review and adr_drift must agree on where ADRs live."""
    import adr_corpus

    tree = ast.parse(
        (REPO / "src/claude/skills/adr-review/scripts/detect_adr_changes.py").read_text(
            encoding="utf-8"
        )
    )
    review_dirs = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "ADR_DIRECTORIES" for t in node.targets)
    )

    assert set(review_dirs) <= set(adr_corpus.KNOWN_DIRS)
