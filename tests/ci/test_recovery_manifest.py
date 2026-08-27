"""Tests for the fail-closed recovery planner (issue #4835)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS
from scripts.github_core.recovery_manifest import (
    MANIFEST_VERSION,
    dedupe_runs,
    manifest_to_dict,
    plan_recovery,
    run_from_mapping,
    summarize_blast_radius,
)
from tests.ci.bulk_cancel_fixtures import (
    INCIDENT_PR_COUNT,
    OPTIONAL_CONTEXT,
    OPTIONAL_WORKFLOW,
    REQUIRED_CONTEXT,
    REQUIRED_WORKFLOW,
    healthy_subscriptions,
    incident_runs,
    make_run,
    reopened_omitting_subscriptions,
    subscriptions_with,
)

_CLOCK = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def plan(runs, subscriptions, recovery_event):
    """Plan with the pinned ruleset contract and a fixed clock."""
    return plan_recovery(
        runs,
        required=REQUIRED_CONTEXTS,
        subscriptions=subscriptions,
        recovery_event=recovery_event,
        repository="rjmurillo/ai-agents",
        now=_CLOCK,
    )


class TestRequiredContextGating:
    def test_required_run_is_verified_when_the_workflow_subscribes(self):
        manifest = plan(
            [make_run(1, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)],
            healthy_subscriptions(),
            "reopened",
        )

        assert manifest.is_safe is True
        assert manifest.entries[0].recovery_event == "reopened"

    def test_required_run_blocks_when_the_workflow_omits_reopened(self):
        manifest = plan(
            [make_run(1, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)],
            reopened_omitting_subscriptions(),
            "reopened",
        )

        assert manifest.is_safe is False
        reason = manifest.blocked[0].blocked_reason or ""
        assert "does not subscribe to 'reopened'" in reason
        assert "opened, synchronize" in reason

    def test_the_same_run_passes_under_a_synchronize_recovery_plan(self):
        manifest = plan(
            [make_run(1, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)],
            reopened_omitting_subscriptions(),
            "synchronize",
        )

        assert manifest.is_safe is True

    def test_required_run_blocks_when_no_recovery_event_is_named(self):
        manifest = plan(
            [make_run(1, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)],
            healthy_subscriptions(),
            None,
        )

        assert manifest.is_safe is False
        assert "no recovery event was named" in (manifest.blocked[0].blocked_reason or "")

    def test_required_run_blocks_when_the_workflow_definition_is_unknown(self):
        manifest = plan(
            [make_run(1, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)],
            {},
            "reopened",
        )

        assert manifest.is_safe is False
        assert "no workflow definition found" in (
            manifest.blocked[0].blocked_reason or ""
        )

    def test_non_required_run_needs_no_recovery_event(self):
        manifest = plan(
            [make_run(1, workflow=OPTIONAL_WORKFLOW, context=OPTIONAL_CONTEXT)],
            {},
            None,
        )

        assert manifest.is_safe is True
        assert manifest.entries[0].recovery_event is None
        assert manifest.entries[0].required_contexts == ()
        assert manifest.entries[0].other_contexts == (OPTIONAL_CONTEXT,)

    def test_rerun_is_accepted_for_a_workflow_with_no_pull_request_trigger(self):
        manifest = plan(
            [make_run(1, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)],
            subscriptions_with({REQUIRED_WORKFLOW: []}),
            "rerun",
        )

        assert manifest.is_safe is True

    def test_unknown_recovery_event_raises_instead_of_blocking_confusingly(self):
        with pytest.raises(ValueError, match="unknown recovery event"):
            plan([make_run(1)], healthy_subscriptions(), "closed")

    def test_a_run_publishing_both_required_and_optional_contexts_is_gated(self):
        run = make_run(1, workflow=REQUIRED_WORKFLOW)
        mixed = run.__class__(
            run_id=run.run_id,
            workflow_name=run.workflow_name,
            pr_number=run.pr_number,
            branch=run.branch,
            event=run.event,
            status=run.status,
            contexts=(REQUIRED_CONTEXT, OPTIONAL_CONTEXT),
        )

        manifest = plan([mixed], reopened_omitting_subscriptions(), "reopened")

        assert manifest.is_safe is False
        assert manifest.entries[0].required_contexts == (REQUIRED_CONTEXT,)
        assert manifest.entries[0].other_contexts == (OPTIONAL_CONTEXT,)


class TestBlastRadius:
    def test_the_41_pr_fixture_reports_its_shape(self):
        runs = incident_runs()

        radius = summarize_blast_radius(runs, REQUIRED_CONTEXTS)

        assert radius.pr_count == INCIDENT_PR_COUNT
        assert radius.branch_count == INCIDENT_PR_COUNT
        assert radius.run_count == INCIDENT_PR_COUNT * 3
        assert radius.workflow_count == 3
        assert radius.required_context_count == 2
        assert radius.queued_runs + radius.in_progress_runs == radius.run_count

    def test_duplicate_run_ids_do_not_inflate_the_radius(self):
        duplicated = [make_run(7), make_run(7), make_run(8)]

        manifest = plan(duplicated, healthy_subscriptions(), "reopened")

        assert manifest.blast_radius.run_count == 2
        assert len(manifest.entries) == 2

    def test_dedupe_keeps_the_first_occurrence(self):
        first = make_run(7, branch="first")
        second = make_run(7, branch="second")

        assert dedupe_runs([first, second]) == [first]

    def test_empty_inventory_reports_zeroes_rather_than_failing(self):
        manifest = plan([], healthy_subscriptions(), "reopened")

        assert manifest.blast_radius.run_count == 0
        assert manifest.is_safe is True

    def test_duplicate_workflow_names_on_one_pr_count_as_two_runs(self):
        runs = [
            make_run(1, workflow=REQUIRED_WORKFLOW, pr_number=5),
            make_run(2, workflow=REQUIRED_WORKFLOW, pr_number=5),
        ]

        radius = summarize_blast_radius(runs, REQUIRED_CONTEXTS)

        assert radius.run_count == 2
        assert radius.workflow_count == 1
        assert radius.pr_count == 1


class TestRunFromMapping:
    def test_builds_a_run_from_a_well_formed_record(self):
        run = run_from_mapping(
            {
                "run_id": "42",
                "workflow_name": "Validate PR",
                "pr_number": 7,
                "branch": "feat/x",
                "event": "synchronize",
                "status": "queued",
                "contexts": ["Validate PR"],
            }
        )

        assert run.run_id == 42
        assert run.contexts == ("Validate PR",)

    @pytest.mark.parametrize("missing", ["run_id", "contexts", "branch", "status"])
    def test_missing_field_raises_rather_than_defaulting(self, missing: str):
        record = {
            "run_id": 1,
            "workflow_name": "Validate PR",
            "pr_number": 7,
            "branch": "feat/x",
            "event": "synchronize",
            "status": "queued",
            "contexts": ["Validate PR"],
        }
        del record[missing]

        with pytest.raises(ValueError, match="malformed workflow run record"):
            run_from_mapping(record)

    def test_string_contexts_value_raises_instead_of_splitting_into_characters(self):
        with pytest.raises(ValueError, match="contexts must be a list"):
            run_from_mapping(
                {
                    "run_id": 1,
                    "workflow_name": "Validate PR",
                    "pr_number": 7,
                    "branch": "feat/x",
                    "event": "synchronize",
                    "status": "queued",
                    "contexts": "Validate PR",
                }
            )

    def test_non_numeric_run_id_raises(self):
        with pytest.raises(ValueError):
            run_from_mapping(
                {
                    "run_id": "not-a-number",
                    "workflow_name": "Validate PR",
                    "pr_number": 7,
                    "branch": "feat/x",
                    "event": "synchronize",
                    "status": "queued",
                    "contexts": [],
                }
            )


class TestSerialization:
    def test_manifest_dict_carries_the_regeneration_inputs(self):
        manifest = plan(
            [make_run(9, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)],
            healthy_subscriptions(),
            "reopened",
        )

        payload = manifest_to_dict(manifest)

        assert payload["version"] == MANIFEST_VERSION
        assert payload["recovery_event"] == "reopened"
        assert payload["safe"] is True
        assert payload["generated_at"] == _CLOCK.isoformat()
        entry = payload["entries"][0]
        assert entry["run_id"] == 9
        assert entry["required_contexts"] == [REQUIRED_CONTEXT]
        assert entry["verified"] is True

    def test_blocked_entry_records_its_reason_in_the_manifest(self):
        manifest = plan(
            [make_run(9, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)],
            reopened_omitting_subscriptions(),
            "reopened",
        )

        payload = manifest_to_dict(manifest)

        assert payload["safe"] is False
        assert payload["entries"][0]["blocked_reason"]
