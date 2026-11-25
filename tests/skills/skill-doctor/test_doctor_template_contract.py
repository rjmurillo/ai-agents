"""Verify canonical template and generated entry points remain synchronized."""

import ast
from pathlib import Path

import yaml

from tests.skills._template_contract import assert_template_owned_contract

REPO = Path(__file__).resolve().parents[3]


def _step_1a() -> str:
    text = (REPO / "templates/skills/skill-doctor.SKILL.md.tmpl").read_text(encoding="utf-8")
    return text.split("### Step 1a: ADR drift", 1)[1].split("\n### ", 1)[0]


def _reference_section(heading: str) -> str:
    reference = (REPO / "src/claude/skills/skill-doctor/references/adr-drift.md").read_text(
        encoding="utf-8"
    )
    return reference.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


def test_skill_doctor_template_contract() -> None:
    assert_template_owned_contract("skill-doctor")


def test_template_routes_adr_drift_to_its_step() -> None:
    """The ADR drift trigger, intent, fast path, and Step 1a all ship in the template."""
    text = (REPO / "templates/skills/skill-doctor.SKILL.md.tmpl").read_text(encoding="utf-8")
    frontmatter, body = text.split("\n---\n", 1)

    meta = yaml.safe_load(frontmatter.removeprefix("---\n"))

    assert "`check ADR drift`" in meta["description"]
    assert "check ADR drift" in meta["metadata"]["routing"]["intents"]
    assert "- `check ADR drift`" in body.split("## Triggers", 1)[1].split("\n## ", 1)[0]
    assert "#### ADR-only fast path" in body
    assert "### Step 1a: ADR drift" in body
    assert "adr_drift.py" in body.split("## Scripts", 1)[1].split("\n## ", 1)[0]


def test_step_1a_reports_undocumented_decisions_unavailable_without_bootstrap() -> None:
    """A missing skill-bootstrap is reported as UNAVAILABLE in Step 1a itself."""
    step = _step_1a()

    assert '"Undocumented decisions: UNAVAILABLE" and continue' in step
    assert "exits 2" in step and "`ptk_run:`" in step
    assert "PowerShell form" in step and "Git Bash" in step
    assert "```powershell" in _reference_section("Commands")
    assert "Without Git Bash" in _reference_section("Workflow")


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


def test_step_1a_points_to_a_workflow_that_holds_the_moved_steps() -> None:
    """Step 1a defers to the reference Workflow, which keeps every command it moved."""
    step = _step_1a()
    workflow = _reference_section("Workflow")

    assert "follow the Workflow in `$SKILL_ROOT/references/adr-drift.md`" in step
    assert "`--all-conversations`" in workflow
    assert 'mkdir -p "$REPORT_DIR/adr_drift"' in workflow
    assert 'adr_drift.py" scan --repo "$REPO"' in workflow
    assert "bootstrap_adr.py scan --repo" in workflow
    assert "<repo-slug>-decisions.json" in workflow
    assert "references/report-schema.md" in workflow


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
