"""Path-filter provenance tests for the CLI smoke workflow (REQ-047 AC12).

The filter script must come from the base commit, never from the pull request
tree, or a fork PR could edit it to return ``run=false``.
"""

from __future__ import annotations

import shlex
from typing import Any

from tests.lib.cli_smoke_workflow import (
    BASE_CHECKOUT_PATH,
    _checkouts,
    _step_by_name,
)

pytest_plugins = ["tests.lib.cli_smoke_fixtures"]


FILTER_SCRIPT = "scripts/validation/cli_smoke_paths.py"


def test_path_filter_script_comes_from_the_base_commit(workflow_doc: dict[Any, Any]) -> None:
    """REQ-047 AC12: a fork PR cannot edit the filter to return run=false.

    The script is checked out from the pull request base SHA into its own
    directory and executed from there with isolated mode (``-I``), so a
    ``sitecustomize.py`` or a ``PYTHONPATH`` shadow in the PR tree cannot run.
    """
    job = workflow_doc["jobs"]["changes"]
    base_checkout = next(c for c in _checkouts(job) if c.get("with", {}).get("path"))
    steps = job["steps"]
    filter_step = _step_by_name(job, "Decide whether the smoke must run")
    arguments = shlex.split(filter_step["run"])

    assert "github.event.pull_request.base.sha" in base_checkout["with"]["ref"]
    assert base_checkout["with"]["path"] == BASE_CHECKOUT_PATH
    assert base_checkout["with"]["persist-credentials"] is False
    assert FILTER_SCRIPT in base_checkout["with"]["sparse-checkout"]
    assert steps.index(base_checkout) < steps.index(filter_step)
    assert arguments[:3] == ["python3", "-I", f"{BASE_CHECKOUT_PATH}/{FILTER_SCRIPT}"]


def test_path_filter_diffs_the_pull_request_tree_not_the_base_copy(
    workflow_doc: dict[Any, Any],
) -> None:
    """Edge: the base copy only supplies code; git diff runs in the PR checkout."""
    job = workflow_doc["jobs"]["changes"]
    pr_checkout = next(c for c in _checkouts(job) if not c.get("with", {}).get("path"))
    arguments = shlex.split(_step_by_name(job, "Decide whether the smoke must run")["run"])

    assert pr_checkout["with"]["fetch-depth"] == 0
    assert arguments[arguments.index("--repo-root") + 1] == "$GITHUB_WORKSPACE"


def test_no_step_runs_the_filter_from_the_pull_request_tree(
    workflow_doc: dict[Any, Any],
) -> None:
    """Negative: every execution of the filter goes through the base copy."""
    for job_name, job in workflow_doc["jobs"].items():
        for step in job["steps"]:
            for line in str(step.get("run", "")).splitlines():
                if FILTER_SCRIPT not in line or "python" not in line:
                    continue
                assert f"{BASE_CHECKOUT_PATH}/{FILTER_SCRIPT}" in line, (job_name, line)
