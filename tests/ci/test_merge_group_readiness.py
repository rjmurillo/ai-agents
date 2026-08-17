# taste-lint: ignore file-size, this test needs every required-context contract
# and mutation control together so a workflow change cannot bypass the queue.

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, TypedDict

import pytest
import yaml

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# Only workflows that produce a required context need a merge_group trigger.
# AI PR reviews and memory citation validation are advisory and therefore absent.
REQUIRED_WORKFLOWS = {
    "ai-spec-validation.yml",
    "codeql-analysis.yml",
    "pr-validation.yml",
    "pytest.yml",
    "semantic-pr-title-check.yml",
    "validate-generated-agents.yml",
    "validate-paths.yml",
    "validate-plugin-version-bump.yml",
}

REQUIRED_PRODUCERS = {
    "ai-spec-validation.yml": {"validate-spec": {"Validate Spec Coverage"}},
    "codeql-analysis.yml": {
        "analyze": {"Analyze (actions)", "Analyze (python)"},
    },
    "pr-validation.yml": {"validate-pr": {"Validate PR"}},
    "pytest.yml": {"test-result": {"Run Python Tests"}},
    "semantic-pr-title-check.yml": {"main": {"Validate PR title"}},
    "validate-generated-agents.yml": {
        "validate": {"Validate Generated Files"},
    },
    "validate-paths.yml": {"validate": {"Validate Path Normalization"}},
    "validate-plugin-version-bump.yml": {
        "validate": {"Validate Plugin Version Bump"},
    },
}

FILTERED_REAL_WORKFLOWS = {
    "codeql-analysis.yml": ("check-paths", "should-run-analysis"),
    "pytest.yml": ("check-paths", "python-changed"),
    "validate-generated-agents.yml": ("check-paths", "should-run-agents"),
    "validate-paths.yml": ("check-paths", "should-run-validation"),
    "validate-plugin-version-bump.yml": (
        "check-paths",
        "should-run-version-bump",
    ),
}


class SkipPolicy(TypedDict):
    gate: str | None
    indirect: set[str]
    direct: set[str]


SKIPPED_PRODUCERS: dict[str, SkipPolicy] = {
    "ai-spec-validation.yml": {
        "gate": None,
        "indirect": set(),
        "direct": {"validate-spec"},
    },
}

IN_JOB_BYPASS = {
    "pr-validation.yml": ("validate-pr", "merge_group"),
    "semantic-pr-title-check.yml": ("main", "merge_group"),
}

PR_REAL_JOBS = {
    "ai-spec-validation.yml": {"validate-spec"},
    "pr-validation.yml": {"validate-pr"},
    "pytest.yml": {"test-result"},
    "semantic-pr-title-check.yml": {"main"},
}

PR_REAL_JOB_MARKERS = {
    "ai-spec-validation.yml": {
        "validate-spec": "scripts/ci/spec_extract_refs.py",
    },
    "pr-validation.yml": {
        "validate-pr": "scripts/ci/enforce_pr_validation.py",
    },
    "pytest.yml": {
        "test-result": "scripts/ci/require_job_results.py",
    },
    "semantic-pr-title-check.yml": {
        "main": "amannn/action-semantic-pull-request",
    },
}


def _load_workflow(name: str) -> dict[Any, Any]:
    loaded = yaml.safe_load((WORKFLOW_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    triggers = workflow.get(True, workflow.get("on"))
    assert isinstance(triggers, dict)
    return triggers


def _job_names(job: dict[str, Any]) -> set[str]:
    name = str(job.get("name", ""))
    include = ((job.get("strategy") or {}).get("matrix") or {}).get("include")
    if "${{ matrix.language }}" in name and isinstance(include, list):
        return {
            name.replace("${{ matrix.language }}", str(entry["language"]))
            for entry in include
        }
    return {name}


def _readiness_errors(workflows: dict[str, dict[Any, Any]]) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_WORKFLOWS:
        workflow = workflows[name]
        merge_group = _triggers(workflow).get("merge_group", ...)
        if merge_group is ...:
            errors.append(f"{name}: missing merge_group trigger")
        elif not isinstance(merge_group, dict):
            errors.append(f"{name}: merge_group target branch is unrestricted")
        else:
            if merge_group.get("branches") != ["main"]:
                errors.append(f"{name}: merge_group does not target main")
            if {"paths", "paths-ignore"} & merge_group.keys():
                errors.append(f"{name}: merge_group trigger has a path filter")

        concurrency = workflow.get("concurrency")
        if isinstance(concurrency, dict) and "github.ref" not in str(
            concurrency.get("group", "")
        ):
            errors.append(f"{name}: concurrency omits github.ref")

    errors.extend(_queue_push_errors(workflows))
    errors.extend(_filtered_workflow_errors(workflows))
    errors.extend(_producer_errors(workflows))
    errors.extend(_skipped_producer_errors(workflows))
    errors.extend(_in_job_bypass_errors(workflows))
    errors.extend(_pull_request_work_errors(workflows))
    return errors


def _queue_push_errors(
    workflows: dict[str, dict[Any, Any]],
) -> list[str]:
    errors: list[str] = []
    for name, workflow in workflows.items():
        push = _triggers(workflow).get("push", ...)
        if push is ...:
            continue
        if not isinstance(push, dict):
            errors.append(f"{name}: push matches merge queue branches")
            continue
        branches = push.get("branches")
        ignored = push.get("branches-ignore", [])
        if not branches and "gh-readonly-queue/**" not in ignored:
            errors.append(f"{name}: push matches merge queue branches")
    return errors


def _filtered_workflow_errors(
    workflows: dict[str, dict[Any, Any]],
) -> list[str]:
    errors: list[str] = []
    for name, (job_id, output_name) in FILTERED_REAL_WORKFLOWS.items():
        job = workflows[name]["jobs"][job_id]
        output = str((job.get("outputs") or {}).get(output_name, ""))
        determine_steps = [
            step
            for step in job.get("steps", [])
            if step.get("run")
            == "python3 scripts/workflows/determine_should_run_from_filters.py"
        ]
        if len(determine_steps) != 1:
            errors.append(f"{name}: missing shared event policy")
            continue
        env = determine_steps[0].get("env") or {}
        if "merge_group" not in str(env.get("FORCE_RUN_EVENTS", "")).split(","):
            errors.append(f"{name}: merge_group does not force real work")
        if "steps.determine.outputs" not in output:
            errors.append(f"{name}: output bypasses shared event policy")
    return errors


def _producer_errors(
    workflows: dict[str, dict[Any, Any]],
) -> list[str]:
    errors: list[str] = []
    declared_contexts: set[str] = set()
    for name, expected_jobs in REQUIRED_PRODUCERS.items():
        jobs = workflows[name]["jobs"]
        for job_id, expected_names in expected_jobs.items():
            job = jobs.get(job_id)
            if not isinstance(job, dict):
                errors.append(f"{name}: missing required producer {job_id}")
                continue
            if _job_names(job) != expected_names:
                errors.append(f"{name}: {job_id} required names drifted")
            if str(job.get("if", "")).strip() in {"false", "${{ false }}"}:
                errors.append(f"{name}: {job_id} is unreachable")
            declared_contexts.update(expected_names)

        counts: dict[str, int] = {}
        for job in jobs.values():
            if not isinstance(job, dict):
                continue
            for context in _job_names(job) & REQUIRED_CONTEXTS:
                counts[context] = counts.get(context, 0) + 1
        for context, count in counts.items():
            if count > 1 and (name, context) != (
                "pytest.yml",
                "Run Python Tests",
            ):
                errors.append(f"{name}: duplicate required context {context}")

    if declared_contexts != REQUIRED_CONTEXTS:
        errors.append("required context inventory drifted")
    return errors


def _skipped_producer_errors(
    workflows: dict[str, dict[Any, Any]],
) -> list[str]:
    errors: list[str] = []
    marker = "github.event_name != 'merge_group'"
    for name, policy in SKIPPED_PRODUCERS.items():
        jobs = workflows[name]["jobs"]
        gate_id = policy["gate"]
        if gate_id and marker not in str(jobs[gate_id].get("if", "")):
            errors.append(f"{name}: merge_group gate is missing")
        for job_id in policy["indirect"]:
            needs = jobs[job_id].get("needs", [])
            if isinstance(needs, str):
                needs = [needs]
            if gate_id not in needs:
                errors.append(f"{name}: {job_id} bypasses merge_group gate")
        for job_id in policy["direct"]:
            if marker not in str(jobs[job_id].get("if", "")):
                errors.append(f"{name}: {job_id} runs on merge_group")
    return errors


def _pull_request_work_errors(
    workflows: dict[str, dict[Any, Any]],
) -> list[str]:
    errors: list[str] = []
    for name, job_ids in PR_REAL_JOBS.items():
        workflow = workflows[name]
        if "pull_request" not in _triggers(workflow):
            errors.append(f"{name}: pull_request trigger removed")
        for job_id in job_ids:
            job = workflow["jobs"].get(job_id)
            if not isinstance(job, dict):
                errors.append(f"{name}: missing real job {job_id}")
                continue
            marker = PR_REAL_JOB_MARKERS[name][job_id]
            steps = job.get("steps", [])
            if not any(
                marker in str(step.get("uses", ""))
                or marker in str(step.get("run", ""))
                for step in steps
            ):
                errors.append(f"{name}: real job {job_id} lost its required action")
    return errors


def _in_job_bypass_errors(
    workflows: dict[str, dict[Any, Any]],
) -> list[str]:
    errors: list[str] = []
    for name, (job_id, marker) in IN_JOB_BYPASS.items():
        job = workflows[name]["jobs"][job_id]
        if "if" in job:
            errors.append(f"{name}: required job is conditional")
        steps = job.get("steps", [])
        if not any(marker in str(step) for step in steps):
            errors.append(f"{name}: merge_group bypass step is missing")
        if name == "pr-validation.yml":
            base_refs = [
                str((step.get("env") or {}).get("BASE_REF", ""))
                for step in steps
                if "BASE_REF" in (step.get("env") or {})
            ]
            if not base_refs or any(
                "github.event.repository.default_branch" not in base_ref
                for base_ref in base_refs
            ):
                errors.append(f"{name}: merge_group base ref fallback is missing")
    return errors


def _current_workflows() -> dict[str, dict[Any, Any]]:
    return {name: _load_workflow(name) for name in REQUIRED_WORKFLOWS}


def test_required_checks_are_merge_group_ready() -> None:
    assert _readiness_errors(_current_workflows()) == []


@pytest.mark.parametrize(
    ("workflow_name", "mutation", "expected", "job_id"),
    [
        (
            "validate-paths.yml",
            "drop-trigger",
            "missing merge_group trigger",
            None,
        ),
        (
            "pytest.yml",
            "drop-force-event",
            "merge_group does not force real work",
            None,
        ),
        (
            "pr-validation.yml",
            "drop-bypass-marker",
            "merge_group bypass step is missing",
            None,
        ),
        (
            "ai-spec-validation.yml",
            "erase-required-marker",
            "real job validate-spec lost its required action",
            "validate-spec",
        ),
        (
            "pr-validation.yml",
            "erase-required-marker",
            "real job validate-pr lost its required action",
            "validate-pr",
        ),
        (
            "pytest.yml",
            "erase-required-marker",
            "real job test-result lost its required action",
            "test-result",
        ),
        (
            "semantic-pr-title-check.yml",
            "erase-required-marker",
            "real job main lost its required action",
            "main",
        ),
        (
            "pytest.yml",
            "bare-push",
            "push matches merge queue branches",
            None,
        ),
        (
            "validate-paths.yml",
            "remove-producer",
            "missing required producer validate",
            None,
        ),
        (
            "pr-validation.yml",
            "duplicate-context",
            "duplicate required context Validate PR",
            None,
        ),
        (
            "validate-generated-agents.yml",
            "false-producer",
            "validate is unreachable",
            None,
        ),
        (
            "pr-validation.yml",
            "drop-base-fallback",
            "merge_group base ref fallback is missing",
            None,
        ),
    ],
)
def test_structural_negative_controls(
    workflow_name: str,
    mutation: str,
    expected: str,
    job_id: str | None,
) -> None:
    workflows = copy.deepcopy(_current_workflows())
    workflow = workflows[workflow_name]

    if mutation == "drop-trigger":
        _triggers(workflow).pop("merge_group")
    elif mutation == "drop-force-event":
        steps = workflow["jobs"]["check-paths"]["steps"]
        determine = next(step for step in steps if step.get("id") == "determine")
        determine["env"]["FORCE_RUN_EVENTS"] = ""
    elif mutation == "drop-bypass-marker":
        step = workflow["jobs"]["validate-pr"]["steps"][1]
        step["run"] = str(step["run"]).replace("merge_group", "pull_request")
        step["env"]["EVENT_NAME"] = "pull_request"
    elif mutation == "erase-required-marker":
        assert job_id is not None
        marker = PR_REAL_JOB_MARKERS[workflow_name][job_id]
        for step in workflow["jobs"][job_id]["steps"]:
            for key in ("uses", "run"):
                if key in step:
                    step[key] = str(step[key]).replace(marker, "removed-required-marker")
    elif mutation == "drop-ref":
        workflow["concurrency"]["group"] = "ai-quality-static"
    elif mutation == "bare-push":
        _triggers(workflow)["push"] = None
    elif mutation == "remove-producer":
        workflow["jobs"].pop("validate")
    elif mutation == "duplicate-context":
        workflow["jobs"]["duplicate"] = {
            "name": "Validate PR",
            "runs-on": "ubuntu-latest",
            "steps": [{"run": "echo duplicate"}],
        }
    elif mutation == "false-producer":
        workflow["jobs"]["validate"]["if"] = "false"
    elif mutation == "drop-base-fallback":
        for step in workflow["jobs"]["validate-pr"]["steps"]:
            env = step.get("env") or {}
            if "BASE_REF" in env:
                env["BASE_REF"] = "${{ github.base_ref }}"
    else:  # pragma: no cover
        raise AssertionError(f"unknown mutation: {mutation}")

    assert any(expected in error for error in _readiness_errors(workflows))
