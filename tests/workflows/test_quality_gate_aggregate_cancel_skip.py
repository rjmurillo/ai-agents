"""Regression tests for #2347: stale BLOCKED status from cancelled runs.

When the ``AI PR Quality Gate`` workflow gets cancelled by concurrency
(``cancel-in-progress: true``), the upstream review jobs end with
``cancelled``. If the ``aggregate`` job runs anyway (``if: always()``),
its ``check_critical_failures`` step exits 1 because some verdicts are
missing, and GitHub records ``Aggregate Results: failure`` against the
PR head SHA. If the superseding run is itself cancelled before it
completes, that stale failure persists and leaves the PR
``mergeStateStatus=BLOCKED`` until a no-op commit refreshes the SHA.

The fix is to gate the aggregate job with ``if: always() && !cancelled()``
so a cancelled run produces no status check at all, letting the next
non-cancelled run be the authoritative one.

This test pins the gate so future edits can't silently drop the
``!cancelled()`` guard and reintroduce #2347.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ai-pr-quality-gate.yml"
SESSION_WORKFLOW_PATH = (
    REPO_ROOT / ".github" / "workflows" / "ai-session-protocol.yml"
)


@pytest.fixture(scope="module")
def workflow() -> dict:
    assert WORKFLOW_PATH.is_file(), f"missing workflow file: {WORKFLOW_PATH}"
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def aggregate_job(workflow: dict) -> dict:
    jobs = workflow["jobs"]
    assert "aggregate" in jobs, "aggregate job missing from workflow"
    return jobs["aggregate"]


class TestAggregateCancelSkip:
    def test_required_result_contexts_are_unique(self) -> None:
        locations: dict[str, list[tuple[str, str]]] = {
            "Aggregate Results": [],
            "Session Protocol Results": [],
        }
        workflows_dir = REPO_ROOT / ".github" / "workflows"
        for path in sorted(workflows_dir.glob("*.y*ml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            for job_id, job in (data.get("jobs") or {}).items():
                if isinstance(job, dict) and job.get("name") in locations:
                    locations[job["name"]].append((path.name, job_id))

        assert locations == {
            "Aggregate Results": [("ai-pr-quality-gate.yml", "aggregate")],
            "Session Protocol Results": [("ai-session-protocol.yml", "aggregate")],
        }

    def test_aggregate_job_gate_skips_on_cancellation(self, aggregate_job: dict) -> None:
        """The aggregate job must skip when the workflow is being cancelled.

        Without ``!cancelled()`` a concurrency-cancelled run would still
        evaluate the aggregate step, find missing verdict artifacts, and
        post ``Aggregate Results: failure`` to the PR head SHA -- which
        is the #2347 stale-blocked bug.
        """
        gate = aggregate_job.get("if", "")
        # Both pieces must be present. We accept either ``!cancelled()``
        # or the equivalent ``cancelled() == false`` form so cosmetic
        # rewrites don't break the test, but the semantic guard must hold.
        assert "always()" in gate, f"aggregate gate must keep always(): {gate!r}"
        assert (
            "!cancelled()" in gate or "cancelled() == false" in gate
        ), (
            "aggregate gate must guard on !cancelled() to prevent #2347 "
            f"(stale BLOCKED status from concurrency-cancelled runs): {gate!r}"
        )

    def test_session_protocol_result_skips_on_cancellation(self) -> None:
        session_workflow = yaml.safe_load(
            SESSION_WORKFLOW_PATH.read_text(encoding="utf-8")
        )
        gate = session_workflow["jobs"]["aggregate"].get("if", "")
        assert "always()" in gate
        assert "!cancelled()" in gate or "cancelled() == false" in gate

    def test_session_prerequisite_script_runs_after_checkout(self) -> None:
        session_workflow = yaml.safe_load(
            SESSION_WORKFLOW_PATH.read_text(encoding="utf-8")
        )
        steps = session_workflow["jobs"]["aggregate"]["steps"]
        names = [step.get("name") for step in steps]
        assert names.index("Checkout repository") < names.index(
            "Check if aggregation needed"
        )

    def test_session_prerequisite_outputs_are_wired(self) -> None:
        session_workflow = yaml.safe_load(
            SESSION_WORKFLOW_PATH.read_text(encoding="utf-8")
        )
        steps = session_workflow["jobs"]["aggregate"]["steps"]
        prerequisite = next(
            step for step in steps if step.get("name") == "Check if aggregation needed"
        )
        aggregate = next(
            step for step in steps if step.get("name") == "Aggregate Verdicts"
        )

        assert prerequisite["env"]["VALIDATE_RESULT"] == "${{ needs.validate.result }}"
        assert (
            prerequisite["env"]["SESSION_FILES"]
            == "${{ needs.detect-changes.outputs.session_files }}"
        )
        assert (
            aggregate["env"]["EXPECTED_RESULTS"]
            == "${{ steps.should-run-protocol.outputs.expected_results }}"
        )
        assert (
            aggregate["env"]["EXPECTED_ARTIFACTS"]
            == "${{ steps.should-run-protocol.outputs.expected_artifacts }}"
        )

    def test_concurrency_still_cancels_in_progress(self, workflow: dict) -> None:
        """Concurrency cancel-in-progress must remain enabled.

        The whole point of the fix is to make cancellation safe, not to
        disable it. If someone reverts cancel-in-progress thinking that
        is the fix, this test catches it.
        """
        concurrency = workflow.get("concurrency", {})
        assert concurrency.get("cancel-in-progress") is True, (
            "cancel-in-progress must stay true; the #2347 fix is in the "
            "aggregate gate, not in disabling concurrency cancellation."
        )
