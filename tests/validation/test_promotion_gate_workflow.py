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


def test_the_only_triggers_are_a_manual_dispatch_and_a_call(workflow: dict[str, Any]) -> None:
    """No push, pull request, or schedule can start the gate."""
    # PyYAML reads the bare key `on` as the boolean True (YAML 1.1).
    triggers = next(value for key, value in workflow.items() if key in ("on", True))
    assert set(triggers) == {"workflow_call", "workflow_dispatch"}


def test_the_call_and_the_dispatch_take_the_same_inputs_plus_the_call_only_build_run(
    workflow: dict[str, Any],
) -> None:
    triggers = next(value for key, value in workflow.items() if key in ("on", True))
    called, dispatched = (
        triggers["workflow_call"]["inputs"],
        triggers["workflow_dispatch"]["inputs"],
    )
    assert set(dispatched) == {
        "candidate-sha",
        "candidate-digest",
        "release-tag",
        "mode",
        "attach-manifest",
    }
    assert set(called) == set(dispatched) | {"build-run-id"}
    assert called["attach-manifest"]["default"] is True is dispatched["attach-manifest"]["default"]
    assert called["mode"]["default"] == "advisory" == dispatched["mode"]["default"]
    assert dispatched["mode"]["options"] == ["advisory", "enforcing"]


def test_the_call_exposes_the_verdict_the_publish_job_reads(workflow: dict[str, Any]) -> None:
    triggers = next(value for key, value in workflow.items() if key in ("on", True))
    outputs = triggers["workflow_call"]["outputs"]
    assert set(outputs) == {"verdict", "promoted", "release_eligible"}
    gate_outputs = _jobs(workflow)["gate"]["outputs"]
    for name, spec in outputs.items():
        assert spec["value"] == f"${{{{ jobs.gate.outputs.{name} }}}}"
        assert gate_outputs[name] == f"${{{{ steps.manifest.outputs.{name} }}}}"


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
        f"${{{{ {DEFAULT_BRANCH_ONLY} && inputs.release-tag != '' && inputs.attach-manifest "
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


def test_the_gate_takes_its_mode_from_an_input_and_checks_the_candidate_placement(
    workflow: dict[str, Any],
) -> None:
    step = next(s for s in _jobs(workflow)["gate"]["steps"] if s.get("id") == "manifest")
    command = _normalized(step["run"])
    assert '--mode "$MODE"' in command
    assert step["env"]["MODE"] == "${{ inputs.mode }}"
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


def test_the_fetch_steps_run_before_the_gate_and_are_the_only_ones_with_a_token(
    workflow: dict[str, Any],
) -> None:
    steps = _jobs(workflow)["gate"]["steps"]
    names = [step.get("name") for step in steps]
    assert names.index("Fetch verified evidence") < names.index("Compute the promotion manifest")
    holders = [step["name"] for step in steps if "GH_TOKEN" in step.get("env", {})]
    assert holders == ["Fetch verified evidence", "Fetch the previous promoted manifest"]


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


def test_the_previous_manifest_is_fetched_before_the_gate_reads_it(
    workflow: dict[str, Any],
) -> None:
    steps = _jobs(workflow)["gate"]["steps"]
    names = [step.get("name") for step in steps]
    assert names.index("Fetch the previous promoted manifest") < names.index(
        "Compute the promotion manifest"
    )
    fetch = steps[names.index("Fetch the previous promoted manifest")]
    gate = steps[names.index("Compute the promotion manifest")]
    assert fetch["env"]["RELEASE_TAG"] == "${{ inputs.release-tag }}"
    assert '--output-dir "$RUNNER_TEMP/previous"' in _normalized(fetch["run"])
    assert '--previous-manifest-dir "$RUNNER_TEMP/previous"' in _normalized(gate["run"])
