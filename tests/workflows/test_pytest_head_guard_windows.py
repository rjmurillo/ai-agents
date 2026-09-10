"""Contract tests for the Windows pytest path-contract job.

The Windows job uses a pytest marker (pytest.mark.windows_path) instead of a
hardcoded file list. Adding pytestmark = pytest.mark.windows_path at module
level in any test file automatically includes it in the Windows run (issue #4299).

Issue #5380 moved the invocation behind `scripts/ci/run_pytest_windows.py`,
which discovers the marked modules and narrows collection to them. The marker
property above is unchanged: discovery is still automatic and still needs no
workflow edit. What changed is that the run command now names a helper script,
so "no hardcoded file list" can no longer be checked by the absence of `.py`.
It is checked here as the absence of any `tests/` path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scripts.test_selection import path_policy

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"
_JOB_NAME = "test-windows-pwsh"
_PATHS_FILTER_ACTION = "dorny/paths-filter@"
_POLICY_FILE_INPUT = "scripts/test_selection/path_policy.yml"
_WINDOWS_COMMAND = "uv run --frozen python scripts/ci/run_pytest_windows.py -v"
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


def _step_for(command: str) -> dict[str, Any] | None:
    return next(
        (step for step in _windows_steps() if step.get("run") == command),
        None,
    )


def test_windows_job_name_describes_marker_scope() -> None:
    with _WORKFLOW.open(encoding="utf-8") as handle:
        workflow = yaml.safe_load(handle)

    assert (
        workflow["jobs"][_JOB_NAME]["name"]
        == "Run Windows path-contract tests (pytest.mark.windows_path)"
    )


def test_windows_job_runs_marker_suite() -> None:
    assert _step_for(_WINDOWS_COMMAND) is not None


def test_windows_marker_suite_uses_pwsh_and_python_314() -> None:
    step = _step_for(_WINDOWS_COMMAND)

    assert step is not None
    assert step.get("shell") == "pwsh"
    env = step.get("env")
    assert isinstance(env, dict)
    assert env.get("UV_PYTHON") == "3.14"


def test_windows_marker_suite_remains_blocking() -> None:
    step = _step_for(_WINDOWS_COMMAND)

    assert step is not None
    assert step.get("continue-on-error", False) is False


def test_windows_job_uses_marker_not_hardcoded_files() -> None:
    """The job must run pytest with -m windows_path, not by naming files.

    A hardcoded file list drifts silently; the marker-based approach picks up
    new files automatically (issue #4299). Since issue #5380 the run command
    names one helper script, which is itself a `.py` path, so the check is that
    the command names no test file rather than no `.py` file at all.
    """
    step = _step_for(_WINDOWS_COMMAND)
    assert step is not None, "expected marker-based step; found a hardcoded file list"

    run_cmd: str = step.get("run", "")
    assert "tests/" not in run_cmd and "tests\\" not in run_cmd, (
        f"step run command names test paths, so discovery is no longer automatic: {run_cmd!r}"
    )
    assert run_cmd.count(".py") == 1, (
        f"expected exactly one script path in the run command, got {run_cmd!r}"
    )


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
    # Issue #5318 moved the list into the shared policy file, so the step
    # carries its path rather than the document. Asserting on the loaded
    # entries instead of on the raw text also stops a commented-out line from
    # satisfying a substring check.
    assert filter_steps[0]["with"]["filters"].strip() == str(_POLICY_FILE_INPUT)

    entries = set(path_policy.load_patterns())
    for path in _LEFTHOOK_TRIGGER_PATHS:
        assert path in entries
