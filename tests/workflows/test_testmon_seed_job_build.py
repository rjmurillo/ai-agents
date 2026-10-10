"""The `testmon-seed` job records what the hook would record (issue #6239)."""

from __future__ import annotations

from scripts.validation import git_hook_policy, testmon_seed
from tests.workflows.pytest_workflow_helpers import WORKFLOW_PATH, seed_step


def test_the_build_runs_the_hook_command_with_its_worker_cap() -> None:
    step = seed_step("Build the testmon database")
    command = "uv run --frozen python scripts/validation/git_hook_policy.py pytest"
    assert step["run"].startswith(command)
    assert "::warning::" in step["run"]
    assert "continue-on-error" not in step
    assert step["env"]["AI_AGENTS_PYTEST_WORKER_CAP"] == "4"
    assert step["env"][git_hook_policy.TESTMON_NO_SEED_ENV] == "1"


def test_the_build_never_opts_into_the_full_suite() -> None:
    """The opt-in would build the database without the testmon selection flags."""
    env = seed_step("Build the testmon database")["env"]
    assert git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV not in env


def test_the_artifact_is_named_by_the_function_the_hook_uses() -> None:
    key_step = seed_step("Compute seed artifact name")
    assert "scripts/validation/testmon_seed.py" in key_step["run"]
    assert key_step["id"] == "seed"
    assert (
        seed_step("Upload the testmon database")["with"]["name"] == "${{ steps.seed.outputs.name }}"
    )


def test_the_hook_looks_in_this_workflow_on_main_for_that_prefix() -> None:
    assert testmon_seed.SEED_ARTIFACT_PREFIX == "testmon-db-"
    assert testmon_seed.WORKFLOW_FILE == WORKFLOW_PATH.name
    assert testmon_seed.MAIN_BRANCH == "main"
