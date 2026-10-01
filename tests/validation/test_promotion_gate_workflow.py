"""The promotion gate workflow keeps its privileged path narrow.

Issue #5636, ADR-113 Resolved Question 3. A parsed-YAML test pins the controls
that stop the one write-scoped job from running when it should not, so a future
edit cannot widen it without a suite failure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "promotion-gate.yml"
GUARD = "refs/heads/{0}"


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _jobs(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return workflow["jobs"]


def _normalized(expression: str) -> str:
    return " ".join(str(expression).split())


def test_the_only_trigger_is_a_manual_dispatch(workflow: dict[str, Any]) -> None:
    # PyYAML reads the bare key `on` as the boolean True (YAML 1.1).
    triggers = next(value for key, value in workflow.items() if key in ("on", True))
    assert set(triggers) == {"workflow_dispatch"}


def test_default_permissions_are_empty(workflow: dict[str, Any]) -> None:
    assert workflow["permissions"] == {}


def test_exactly_one_job_holds_a_write_permission(workflow: dict[str, Any]) -> None:
    writers = {
        name
        for name, job in _jobs(workflow).items()
        if any(level == "write" for level in job.get("permissions", {}).values())
    }
    assert writers == {"release-manifest"}


def test_the_write_job_is_scoped_to_contents_only(workflow: dict[str, Any]) -> None:
    assert _jobs(workflow)["release-manifest"]["permissions"] == {"contents": "write"}


DEFAULT_BRANCH_ONLY = (
    "github.ref == format('refs/heads/{0}', github.event.repository.default_branch)"
)


def test_the_gate_job_condition_is_exactly_the_default_branch_guard(
    workflow: dict[str, Any],
) -> None:
    assert _normalized(_jobs(workflow)["gate"]["if"]) == f"${{{{ {DEFAULT_BRANCH_ONLY} }}}}"


def test_the_release_job_condition_is_exactly_the_full_guard(workflow: dict[str, Any]) -> None:
    expected = (
        f"${{{{ {DEFAULT_BRANCH_ONLY} && inputs.release-tag != '' "
        "&& needs.gate.outputs.release_eligible == 'true' }}"
    )
    assert _normalized(_jobs(workflow)["release-manifest"]["if"]) == expected
    assert _jobs(workflow)["release-manifest"]["needs"] == "gate"


def test_the_write_job_checks_out_no_code_and_runs_no_repository_script(
    workflow: dict[str, Any],
) -> None:
    steps = _jobs(workflow)["release-manifest"]["steps"]
    uses = [step.get("uses", "") for step in steps]
    assert not any(item.startswith("actions/checkout") for item in uses)
    runs = [step["run"] for step in steps if "run" in step]
    assert all("scripts/" not in run and "uv " not in run for run in runs)


def test_the_gate_job_is_read_only_and_does_not_persist_credentials(
    workflow: dict[str, Any],
) -> None:
    gate = _jobs(workflow)["gate"]
    assert gate["permissions"] == {"contents": "read", "actions": "read", "checks": "read"}
    checkout = next(s for s in gate["steps"] if s.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["persist-credentials"] is False


def test_the_gate_runs_advisory_and_checks_the_candidate_placement(
    workflow: dict[str, Any],
) -> None:
    step = next(s for s in _jobs(workflow)["gate"]["steps"] if s.get("id") == "manifest")
    command = _normalized(step["run"])
    assert "--mode advisory" in command
    assert "--ancestor-of HEAD" in command
    assert '--expect-tag "$RELEASE_TAG"' in command


def test_inputs_reach_the_shell_only_through_env(workflow: dict[str, Any]) -> None:
    for job in _jobs(workflow).values():
        for step in job["steps"]:
            assert "inputs." not in str(step.get("run", ""))
            assert "github.event.inputs" not in str(step.get("run", ""))


def test_every_action_is_pinned_to_a_full_commit_sha(workflow: dict[str, Any]) -> None:
    for job in _jobs(workflow).values():
        for step in job["steps"]:
            ref = step.get("uses", "")
            if ref and not ref.startswith("./"):
                assert len(ref.split("@")[1]) == 40, ref


def test_the_fetch_step_runs_before_the_gate_and_is_the_only_one_with_a_token(
    workflow: dict[str, Any],
) -> None:
    steps = _jobs(workflow)["gate"]["steps"]
    names = [step.get("name") for step in steps]
    assert names.index("Fetch verified evidence") < names.index("Compute the promotion manifest")
    holders = [step["name"] for step in steps if "GH_TOKEN" in step.get("env", {})]
    assert holders == ["Fetch verified evidence"]


def test_the_fetch_step_reads_the_candidate_from_env_and_names_the_default_branch(
    workflow: dict[str, Any],
) -> None:
    step = next(
        s for s in _jobs(workflow)["gate"]["steps"] if s.get("name") == "Fetch verified evidence"
    )
    assert step["env"]["CANDIDATE_SHA"] == "${{ inputs.candidate-sha }}"
    assert step["env"]["DEFAULT_BRANCH"] == "${{ github.event.repository.default_branch }}"
    command = _normalized(step["run"])
    assert "fetch_promotion_evidence.py" in command
    assert '--evidence-dir "$RUNNER_TEMP/evidence"' in command


def test_no_job_triggers_on_a_pull_request_or_checks_out_a_head_ref(
    workflow: dict[str, Any],
) -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request_target" not in text
    assert "head_ref" not in text
    assert "github.event.pull_request" not in text


def test_the_setup_action_in_the_gate_job_receives_no_token(workflow: dict[str, Any]) -> None:
    steps = _jobs(workflow)["gate"]["steps"]
    setup = next(s for s in steps if s.get("uses") == "./.github/actions/setup-code-env")
    assert setup["with"]["gh-token"] == ""
    assert "secrets." not in WORKFLOW.read_text(encoding="utf-8")
