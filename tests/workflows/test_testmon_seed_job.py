"""The `testmon-seed` job in pytest.yml (issue #6239, ADR-104).

The job builds the database the pre-push hook downloads. It must never gate or
slow `Run Python Tests`, must run only for a push to main (the hook trusts the
artifact because of that), and must record what the hook would record.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.validation import git_hook_policy, testmon_seed

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"
_SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
_JOB = "testmon-seed"


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def job(workflow: dict[str, Any]) -> dict[str, Any]:
    return workflow["jobs"][_JOB]


def _remote_actions(steps: list[dict[str, Any]]) -> set[str]:
    return {step["uses"] for step in steps if "uses" in step and not step["uses"].startswith("./")}


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


def test_the_job_runs_only_for_a_push_to_main(job: dict[str, Any]) -> None:
    condition = re.sub(r"\s+", " ", str(job["if"]))
    assert condition == "github.event_name == 'push' && github.ref == 'refs/heads/main'"


def test_the_job_is_not_a_dependency_of_the_required_chain(workflow: dict[str, Any]) -> None:
    for name, other in workflow["jobs"].items():
        needs = other.get("needs", [])
        needs = [needs] if isinstance(needs, str) else needs
        assert _JOB not in needs, f"{name} waits on the seed job"
    assert _JOB not in workflow["jobs"]["test-result"]["needs"]


def test_the_job_has_no_dependencies_of_its_own(job: dict[str, Any]) -> None:
    """A slow `test` job must not delay the seed, and the seed cannot fail the chain."""
    assert "needs" not in job


def test_the_job_has_a_timeout_that_fits_a_four_vcpu_runner(job: dict[str, Any]) -> None:
    assert 30 < job["timeout-minutes"] <= 90


def test_the_job_is_read_only(job: dict[str, Any]) -> None:
    assert job["permissions"] == {"contents": "read"}


def test_every_action_is_pinned_to_a_commit_sha(job: dict[str, Any]) -> None:
    actions = _remote_actions(job["steps"])
    assert actions
    for action in actions:
        assert _SHA_PIN.match(action), action


def test_the_job_adds_no_action_the_file_does_not_already_use(workflow: dict[str, Any]) -> None:
    others = set()
    for name, other in workflow["jobs"].items():
        if name != _JOB:
            others |= _remote_actions(other["steps"])
    assert _remote_actions(workflow["jobs"][_JOB]["steps"]) <= others


def test_checkout_does_not_persist_credentials(job: dict[str, Any]) -> None:
    checkout = next(
        s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout")
    )
    assert checkout["with"]["persist-credentials"] is False


def test_the_build_runs_the_hook_command_with_its_worker_cap(job: dict[str, Any]) -> None:
    step = _step(job, "Build the testmon database")
    command = "uv run --frozen python scripts/validation/git_hook_policy.py pytest"
    assert step["run"].startswith(command)
    assert "::warning::" in step["run"]
    assert step["env"]["AI_AGENTS_PYTEST_WORKER_CAP"] == "4"
    assert step["env"][git_hook_policy.TESTMON_NO_SEED_ENV] == "1"
    assert "continue-on-error" not in step


def test_the_build_forces_no_full_suite_opt_in(job: dict[str, Any]) -> None:
    """The opt-in would build the database without testmon selection flags."""
    step = _step(job, "Build the testmon database")
    assert git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV not in step.get("env", {})


def test_the_artifact_is_named_by_the_shared_key_function(job: dict[str, Any]) -> None:
    key_step = _step(job, "Compute seed artifact name")
    assert "scripts/validation/testmon_seed.py" in key_step["run"]
    upload = _step(job, "Upload the testmon database")
    assert upload["with"]["name"] == "${{ steps.seed.outputs.name }}"
    assert key_step["id"] == "seed"


def test_the_artifact_name_matches_what_the_hook_looks_for() -> None:
    assert testmon_seed.SEED_ARTIFACT_PREFIX == "testmon-db-"
    assert testmon_seed.WORKFLOW_FILE == _WORKFLOW.name
    assert testmon_seed.MAIN_BRANCH == "main"


def test_the_upload_includes_the_hidden_database_file(job: dict[str, Any]) -> None:
    """upload-artifact skips dotfiles unless told otherwise; the file is `.testmondata`."""
    with_ = _step(job, "Upload the testmon database")["with"]
    assert with_["path"] == testmon_seed.DATABASE_NAME
    assert with_["include-hidden-files"] is True
    assert with_["if-no-files-found"] == "error"


def test_the_upload_runs_after_failed_partitions_but_not_when_cancelled(
    job: dict[str, Any],
) -> None:
    condition = _step(job, "Upload the testmon database")["if"]
    assert "!cancelled()" in condition
    assert "hashFiles('.testmondata')" in condition


def test_the_workflow_still_has_no_pull_request_path_to_the_seed(workflow: dict[str, Any]) -> None:
    """Defense in depth: nothing in the seed job reads a pull request context."""
    text = yaml.safe_dump(workflow["jobs"][_JOB])
    assert "pull_request" not in text
    assert "github.head_ref" not in text
