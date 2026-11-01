"""Every PR-triggered workflow is classified as required or report-only.

REQUIRED_CONTEXTS pins the nine contexts the ruleset requires. Everything else
that runs on a pull request is report-only, and a reader cannot tell that from
the YAML. These tests make the split an explicit list that fails closed: a new
PR-triggered workflow is in neither set until someone decides.

AI workflows are report-only by policy. The model-credential scan below fails if
one is listed as required, or if a workflow that reads a model credential is
labelled deterministic.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ci import ruleset_required_contexts as contract

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
PR_EVENTS = frozenset({"pull_request", "pull_request_target", "merge_group"})
MODEL_MARKERS = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "COPILOT_GITHUB_TOKEN",
    "anthropics/claude-code-action",
    "./.github/actions/ai-review",
)


def _load(path: Path) -> dict[Any, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path.name} did not parse to a mapping"
    return data


def _events(workflow: dict[Any, Any]) -> set[str]:
    # PyYAML reads the bare key `on` as boolean True.
    triggers = workflow.get(True) or workflow.get("on")
    if isinstance(triggers, str):
        return {triggers}
    if isinstance(triggers, list):
        return {str(item) for item in triggers}
    if isinstance(triggers, dict):
        return {str(key) for key in triggers}
    return set()


def _pr_triggered() -> set[str]:
    return {
        path.name
        for path in sorted(WORKFLOW_DIR.glob("*.y*ml"))
        if _events(_load(path)) & PR_EVENTS
    }


def _reads_model_credential(name: str) -> bool:
    text = (WORKFLOW_DIR / name).read_text(encoding="utf-8")
    return any(marker in text for marker in MODEL_MARKERS)


def _matrix_values(matrix: dict[Any, Any], axis: str) -> list[Any]:
    values = list(matrix.get(axis) or [])
    values += [entry[axis] for entry in matrix.get("include") or [] if axis in entry]
    return values


def _job_names(workflow: dict[Any, Any]) -> set[str]:
    names: set[str] = set()
    for key, job in (workflow.get("jobs") or {}).items():
        name = str(job.get("name", key))
        matrix = (job.get("strategy") or {}).get("matrix") or {}
        match = re.fullmatch(r"(.*)\$\{\{\s*matrix\.(\w+)\s*\}\}(.*)", name)
        if match and _matrix_values(matrix, match.group(2)):
            prefix, axis, suffix = match.groups()
            names.update(f"{prefix}{value}{suffix}" for value in _matrix_values(matrix, axis))
        else:
            names.add(name)
    return names


def test_a_workflow_is_never_both_required_and_report_only() -> None:
    assert not contract.REQUIRED_WORKFLOWS & set(contract.REPORT_ONLY_WORKFLOWS)


def test_every_pr_triggered_workflow_is_classified() -> None:
    classified = contract.REQUIRED_WORKFLOWS | set(contract.REPORT_ONLY_WORKFLOWS)
    missing = sorted(_pr_triggered() - classified)
    assert not missing, (
        f"PR-triggered workflows with no classification: {missing}. Add each to "
        "REQUIRED_WORKFLOWS (and pin its context in the ruleset) or to "
        "REPORT_ONLY_WORKFLOWS with a reason, in scripts/ci/ruleset_required_contexts.py."
    )


def test_classification_names_only_pr_triggered_workflows() -> None:
    classified = contract.REQUIRED_WORKFLOWS | set(contract.REPORT_ONLY_WORKFLOWS)
    stale = sorted(classified - _pr_triggered())
    assert not stale, f"classified but not PR-triggered, or deleted: {stale}"


def test_every_required_context_comes_from_a_required_workflow() -> None:
    produced: set[str] = set()
    for name in contract.REQUIRED_WORKFLOWS:
        produced |= _job_names(_load(WORKFLOW_DIR / name))
    missing = sorted(contract.REQUIRED_CONTEXTS - produced)
    assert not missing, f"required contexts no required workflow produces: {missing}"


def test_report_only_workflows_do_not_produce_a_required_context() -> None:
    for name in contract.REPORT_ONLY_WORKFLOWS:
        clash = _job_names(_load(WORKFLOW_DIR / name)) & contract.REQUIRED_CONTEXTS
        assert not clash, f"{name} is report-only but produces required {sorted(clash)}"


@pytest.mark.parametrize("name", sorted(contract.REQUIRED_WORKFLOWS))
def test_required_workflows_read_no_model_credential(name: str) -> None:
    assert not _reads_model_credential(name), f"{name} is required but calls a model"


@pytest.mark.parametrize("name", sorted(contract.REPORT_ONLY_WORKFLOWS))
def test_ai_label_matches_model_credential_use(name: str) -> None:
    labelled_ai = contract.REPORT_ONLY_WORKFLOWS[name] == contract.AI_QUOTA
    uses_model = _reads_model_credential(name)
    if name == "post-pr-retrospective.yml":
        assert uses_model and labelled_ai
        return
    assert labelled_ai == uses_model, (
        f"{name}: labelled AI={labelled_ai} but model credential use={uses_model}"
    )


def test_every_report_only_entry_has_a_reason() -> None:
    assert all(reason.strip() for reason in contract.REPORT_ONLY_WORKFLOWS.values())
