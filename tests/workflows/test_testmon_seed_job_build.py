"""The `testmon-seed` job records what the hook would record (issue #6239)."""

from __future__ import annotations

from scripts.validation import git_hook_policy, testmon_seed
from scripts.validation import testmon_seed_trust as trust
from tests.workflows.pytest_workflow_helpers import WORKFLOW_PATH, seed_job, seed_step


def test_the_build_step_calls_the_tested_script_with_the_cap_and_own_budget() -> None:
    step = seed_step("Build the testmon database")
    assert step["run"] == "uv run --frozen python scripts/validation/testmon_seed_build.py"
    assert "continue-on-error" not in step
    assert step["env"]["AI_AGENTS_PYTEST_WORKER_CAP"] == "4"
    assert step["env"][git_hook_policy.TESTMON_NO_SEED_ENV] == "1"
    budget = int(step["env"][git_hook_policy.TESTMON_SEED_BUDGET_ENV])
    cap_seconds = seed_job()["timeout-minutes"] * 60
    # Past the 780 s suite budget, and leaving the job room for setup and upload.
    assert git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS < budget <= cap_seconds - 120


def test_the_workflow_holds_no_branching_for_the_build_outcome() -> None:
    """The decision lives in testmon_seed_build.py, which has tests (thin workflows)."""
    step = seed_step("Build the testmon database")
    assert step["id"] == "build"
    for fragment in ("if ", "; then", "||", "&&", "GITHUB_OUTPUT"):
        assert fragment not in step["run"]


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
    assert trust.WORKFLOW_FILE == WORKFLOW_PATH.name
    assert trust.MAIN_BRANCH == "main"
