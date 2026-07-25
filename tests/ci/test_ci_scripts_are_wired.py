"""Every guard under scripts/ci must be called by a workflow.

Issue #3329: `ruff_count_ratchet.py` and `adr006_run_block_scanner.py` both
shipped with passing test suites and no caller. Their tests exercised the
interface, so they were green, and the guards protected nothing for weeks. The
count ratchet was also wrong in a way only a real run would surface: it scoped
itself with a directory walk and counted 767 violations where the tracked-file
number was 361.

A unit test cannot catch that class of defect, because the thing that is missing
is the call site. This checks the call site.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_SCRIPTS_DIR = _REPO_ROOT / "scripts" / "ci"
_WORKFLOW_DIRS = (
    _REPO_ROOT / ".github" / "workflows",
    _REPO_ROOT / ".github" / "actions",
)

# Guards that are deliberately not invoked from a workflow. Each needs a reason,
# so that adding one is a decision rather than a way to silence this test.
_NOT_WORKFLOW_INVOKED: dict[str, str] = {}


def _workflow_text() -> str:
    """Every workflow and composite action body, concatenated."""
    parts: list[str] = []
    for directory in _WORKFLOW_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.yml")) + sorted(directory.rglob("*.yaml")):
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _ci_scripts() -> list[Path]:
    if not _CI_SCRIPTS_DIR.is_dir():
        return []
    return [p for p in sorted(_CI_SCRIPTS_DIR.glob("*.py")) if not p.name.startswith("_")]


@pytest.mark.parametrize("script", _ci_scripts(), ids=lambda p: p.name)
def test_ci_script_is_invoked_by_a_workflow(script: Path) -> None:
    if script.name in _NOT_WORKFLOW_INVOKED:
        pytest.skip(_NOT_WORKFLOW_INVOKED[script.name])
    rel = script.relative_to(_REPO_ROOT).as_posix()
    assert rel in _workflow_text(), (
        f"{rel} has no call site in .github/workflows or .github/actions. "
        f"A guard nothing runs is not a guard, and its own tests will stay "
        f"green while it protects nothing (issue #3329). Wire it into a "
        f"workflow, or add it to _NOT_WORKFLOW_INVOKED with a reason."
    )


def test_workflow_yaml_validator_runs_in_ci() -> None:
    """Issue #3330: workflow YAML was checked only by a local hook.

    Named separately from the parametrized case above because the validator does
    not live under scripts/ci, and because the specific requirement is that it
    runs on a path-independent job: a workflow-only PR changes no Python, so
    every path-filtered gate skips it.
    """
    text = _workflow_text()
    assert "scripts/validate_workflows.py" in text, (
        "scripts/validate_workflows.py is invoked only by lefthook, so workflow "
        "YAML lands unvalidated from Renovate, Dependabot, the web editor, the "
        "API, and any clone without hooks installed (issue #3330)."
    )


def test_the_wiring_probe_reads_real_workflow_files() -> None:
    """Guard the guard: an empty corpus would make every case above vacuous."""
    text = _workflow_text()
    assert len(text) > 10_000
    assert re.search(r"^\s*runs-on:", text, re.MULTILINE)
