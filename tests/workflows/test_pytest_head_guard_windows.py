"""Contract tests for the Windows pytest HEAD guard job."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"
_JOB_NAME = "test-windows-pwsh"
_COMMAND = "uv run pytest tests/test_pytest_head_guard.py -v"


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


def _head_guard_step() -> dict[str, Any] | None:
    return next(
        (step for step in _windows_steps() if step.get("run") == _COMMAND),
        None,
    )


def test_windows_job_runs_head_guard_contract() -> None:
    assert _head_guard_step() is not None


def test_windows_head_guard_contract_uses_pwsh_and_python_314() -> None:
    step = _head_guard_step()

    assert step is not None
    assert step.get("shell") == "pwsh"
    env = step.get("env")
    assert isinstance(env, dict)
    assert env.get("UV_PYTHON") == "3.14"


def test_windows_head_guard_contract_remains_blocking() -> None:
    step = _head_guard_step()

    assert step is not None
    assert step.get("continue-on-error", False) is False
