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


def test_step_1a_reports_undocumented_decisions_unavailable_without_bootstrap() -> None:
    """A missing skill-bootstrap is reported as UNAVAILABLE in Step 1a itself."""
    text = (REPO / "templates/skills/skill-doctor.SKILL.md.tmpl").read_text(encoding="utf-8")
    step = text.split("### Step 1a: ADR drift", 1)[1].split("\n### ", 1)[0]

    assert '"Undocumented decisions: UNAVAILABLE" and continue' in step
    assert "exits 2" in step and "`ptk_run:`" in step
    reference = (REPO / "src/claude/skills/skill-doctor/references/adr-drift.md").read_text(
        encoding="utf-8"
    )
    assert "PowerShell form" in step and "Git Bash" in step
    assert "```powershell" in reference.split("## Commands", 1)[1].split("\n## ", 1)[0]


def _module_tuple(relative: str, name: str) -> list[str]:
    """The literal list or tuple assigned to NAME at the top level of a script."""
    tree = ast.parse((REPO / relative).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets: list[ast.expr] = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if node.value is not None and any(
            isinstance(t, ast.Name) and t.id == name for t in targets
        ):
            return list(ast.literal_eval(node.value))
    raise AssertionError(f"{relative} assigns no literal {name}")


def test_known_adr_folders_equal_the_skill_bootstrap_folders() -> None:
    """skill-doctor and skill-bootstrap read the same ADR folders, so one run agrees with itself."""
    bootstrap = _module_tuple(
        "src/claude/skills/skill-bootstrap/scripts/adr_locate.py", "KNOWN_FOLDERS"
    )
    known_dirs = _module_tuple("src/claude/skills/skill-doctor/scripts/adr_corpus.py", "KNOWN_DIRS")

    assert list(known_dirs) == list(bootstrap)


def test_known_adr_folders_cover_the_adr_review_folders() -> None:
    """adr-review and adr_drift must agree on where ADRs live."""
    review_dirs = _module_tuple(
        "src/claude/skills/adr-review/scripts/detect_adr_changes.py", "ADR_DIRECTORIES"
    )
    known_dirs = _module_tuple("src/claude/skills/skill-doctor/scripts/adr_corpus.py", "KNOWN_DIRS")

    assert review_dirs and set(review_dirs) <= set(known_dirs)
