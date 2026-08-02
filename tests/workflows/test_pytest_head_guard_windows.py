"""Contract tests for the Windows pytest HEAD guard job."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"
_JOB_NAME = "test-windows-pwsh"
_PATHS_FILTER_ACTION = "dorny/paths-filter@"
_HEAD_GUARD_COMMAND = "uv run pytest tests/test_pytest_head_guard.py -v"
_LEFTHOOK_COMMAND = "uv run pytest tests/test_lefthook_integration.py -q"
_LEFTHOOK_TRIGGER_PATHS = {
    "lefthook.yml",
    ".config/wt.toml",
    "scripts/bootstrap-vm.sh",
    ".github/actions/setup-code-env/action.yml",
}


def _windows_steps() -> list[dict[str, Any]]:
    with _WORKFLOW.open(encoding="utf-8") as handle:
        workflow = yaml.safe_load(handle)
    assert isinstance(workflow, dict), f"expected {_WORKFLOW} to parse as a mapping"
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "expected workflow jobs to be a mapping"
    job = jobs.get(_JOB_NAME)
    assert isinstance(job, dict), f"expected {_JOB_NAME} job to be a mapping"
    steps = job.get("steps")
    assert isinstance(steps, list), f"expected {_JOB_NAME} steps to be a list"
    return [step for step in steps if isinstance(step, dict)]


def test_windows_job_name_describes_python_and_lefthook_scope() -> None:
    with _WORKFLOW.open(encoding="utf-8") as handle:
        workflow = yaml.safe_load(handle)

    assert (
        workflow["jobs"][_JOB_NAME]["name"]
        == "Run Python and Lefthook Tests (Windows)"
    )


def _step_for(command: str) -> dict[str, Any] | None:
    return next(
        (step for step in _windows_steps() if step.get("run") == command),
        None,
    )


def test_windows_job_runs_head_guard_contract() -> None:
    assert _step_for(_HEAD_GUARD_COMMAND) is not None


def test_windows_head_guard_contract_uses_pwsh_and_python_314() -> None:
    step = _step_for(_HEAD_GUARD_COMMAND)

    assert step is not None
    assert step.get("shell") == "pwsh"
    env = step.get("env")
    assert isinstance(env, dict)
    assert env.get("UV_PYTHON") == "3.14"


def test_windows_head_guard_contract_remains_blocking() -> None:
    step = _step_for(_HEAD_GUARD_COMMAND)

    assert step is not None
    assert step.get("continue-on-error", False) is False


def test_windows_job_runs_lefthook_integration_suite() -> None:
    assert _step_for(_LEFTHOOK_COMMAND) is not None


def test_windows_lefthook_suite_uses_pwsh_and_python_314() -> None:
    step = _step_for(_LEFTHOOK_COMMAND)

    assert step is not None
    assert step.get("shell") == "pwsh"
    env = step.get("env")
    assert isinstance(env, dict)
    assert env.get("UV_PYTHON") == "3.14"


def test_windows_lefthook_suite_remains_blocking() -> None:
    step = _step_for(_LEFTHOOK_COMMAND)

    assert step is not None
    assert step.get("continue-on-error", False) is False


def test_lefthook_runtime_surfaces_trigger_windows_suite() -> None:
    with _WORKFLOW.open(encoding="utf-8") as handle:
        workflow = yaml.safe_load(handle)
    # Select the step by the action it runs. A positional index, or a search for
    # the first step carrying a `with.filters` key, silently picks up whatever
    # step is inserted or grows that key first.
    filter_steps = [
        step
        for step in workflow["jobs"]["check-paths"]["steps"]
        if str(step.get("uses", "")).startswith(_PATHS_FILTER_ACTION)
    ]
    assert len(filter_steps) == 1, f"expected one {_PATHS_FILTER_ACTION} step in check-paths"
    filters = filter_steps[0]["with"]["filters"]

    for path in _LEFTHOOK_TRIGGER_PATHS:
        assert f"- '{path}'" in filters
