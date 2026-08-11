"""Root context changes must execute their byte-budget tests in CI."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    ".claude/CLAUDE.md",
    ".github/copilot-instructions.md",
}


def _workflow(name: str) -> dict:
    return yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    )


def _paths(filters: str, key: str) -> set[str]:
    parsed = yaml.safe_load(filters)
    return set(parsed[key])


def test_pytest_workflow_runs_for_root_context_files() -> None:
    steps = _workflow("pytest.yml")["jobs"]["check-paths"]["steps"]
    filter_step = next(step for step in steps if step.get("id") == "filter")
    paths = _paths(filter_step["with"]["filters"], "python")
    assert ROOT_FILES <= paths


def test_passive_context_workflow_uses_workspace_byte_gate() -> None:
    workflow = _workflow("passive-context-budget.yml")
    check_steps = workflow["jobs"]["check-paths"]["steps"]
    filter_step = next(step for step in check_steps if step.get("id") == "filter")
    filters = filter_step["with"]["filters"]
    assert ROOT_FILES <= _paths(filters, "context")
    assert "scripts/validate_workspace_budget.py" in _paths(filters, "validator")
    validate_steps = workflow["jobs"]["validate-budget"]["steps"]
    run_step = next(step for step in validate_steps if step.get("name") == "Run budget validator")
    assert run_step["run"] == "python3 scripts/validate_workspace_budget.py --path ."
