"""Tests for the fail-closed recovery planner (issue #4835).

Where a run's required-context set comes from, which is the union of the jobs
API and the workflow file, is covered in
``tests/ci/test_recovery_manifest_context_sources.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS
from scripts.github_core.recovery_manifest import (
    MANIFEST_VERSION,
    WorkflowRun,
    dedupe_runs,
    manifest_to_dict,
    run_from_mapping,
    summarize_blast_radius,
)
from scripts.github_core.workflow_event_subscriptions import (
    load_workflow_subscriptions,
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
from tests.ci.bulk_cancel_fixtures import (
    PINNED_CLOCK as _CLOCK,
)
from tests.ci.bulk_cancel_fixtures import (
    plan_with_pinned_contract as plan,
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
            healthy_subscriptions(),
            None,
        )

        assert manifest.is_safe is True
        assert manifest.entries[0].recovery_event is None
        assert manifest.entries[0].required_contexts == ()
        assert manifest.entries[0].other_contexts == (OPTIONAL_CONTEXT,)
        assert manifest.entries[0].verification == "not-required"

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


class TestUnmaterializedJobsFailClosed:
    """A queued run whose jobs have not materialized must not verify as safe.

    2026-08-27 gap in the AI-Spec-Validator's PARTIAL verdict on PR #5357:
    ``run_contexts`` returned ``()`` for a run whose jobs endpoint responded
    with zero records (a live GitHub eventual-consistency race for a run still
    in ``queued`` state, not evidence the run publishes no required context).
    ``_classify`` could not tell that empty-because-unmaterialized apart from
    empty-because-genuinely-no-required-job, and treated both as verified,
    safe to cancel unguarded. This is the same fail-open shape the shared-
    workflow-name fix elsewhere in this PR closed, one layer up.
    """

    def _run(self, *, jobs_verified: bool) -> WorkflowRun:
        """Build the run the live ``--all-open-prs`` path would have produced.

        Same shape either way: a queued run whose resolved ``contexts`` is
        empty. ``jobs_verified`` is the only variable, so any behavior
        difference between the two calls below is attributable to the flag
        alone, not to some other property of the run.
        """
        return WorkflowRun(
            run_id=1,
            workflow_name=REQUIRED_WORKFLOW,
            pr_number=7,
            branch="feat/queued",
            event="synchronize",
            status="queued",
            contexts=(),
            jobs_verified=jobs_verified,
        )

    def test_negative_control_reproduces_the_old_fail_open_bug(self):
        """Mutating back to the pre-fix state: an unmaterialized run reads as
        having no required context and clears unguarded, exactly like the
        code did before ``jobs_verified`` existed (the field always defaulted
        to True, so this is the only state the old code could ever produce).
        """
        run = self._run(jobs_verified=True)

        manifest = plan([run], healthy_subscriptions(), None)

        assert manifest.is_safe is True, (
            "negative control did not reproduce the bug: an unverified-jobs "
            "run with jobs_verified=True still blocked, so the test is not "
            "exercising the code path the fix changes"
        )

    def test_fix_blocks_the_same_run_once_jobs_verified_is_false(self):
        run = self._run(jobs_verified=False)

        manifest = plan([run], healthy_subscriptions(), None)

        assert manifest.is_safe is False
        reason = manifest.blocked[0].blocked_reason or ""
        assert "materialized" in reason
        assert "issue #4835" in reason

    def test_run_from_mapping_defaults_to_jobs_verified_true(self):
        run = run_from_mapping(
            {
                "run_id": 1,
                "workflow_name": REQUIRED_WORKFLOW,
                "pr_number": 7,
                "branch": "feat/x",
                "event": "synchronize",
                "status": "queued",
                "contexts": [],
            }
        )

        assert run.jobs_verified is True


class TestSharedWorkflowName:
    """Two workflow files declaring one name must not clear each other's runs.

    A run record names its workflow, so the planner resolves it by name. When
    two files answer to that name, verifying against whichever one the loader
    read first clears a run whose real workflow cannot be regenerated by the
    named event, which is the incident shape one level up from issue #4835.
    These drive the real loader rather than a hand-built map, because the
    defect lived in the loader and a hand-built map cannot express it.
    """

    def load_pair(self, directory: Path, first_types: str, second_types: str):
        """Write two files declaring REQUIRED_WORKFLOW, then load them."""
        for filename, types in (("a.yml", first_types), ("b.yml", second_types)):
            (directory / filename).write_text(
                f"name: {REQUIRED_WORKFLOW}\n"
                f"on:\n  pull_request:\n    types: {types}\n",
                encoding="utf-8",
            )
        return load_workflow_subscriptions(directory)

    def test_blocks_when_only_one_sharer_subscribes_to_the_recovery_event(
        self, tmp_path: Path
    ):
        subscriptions = self.load_pair(
            tmp_path, "[opened, reopened]", "[opened, synchronize]"
        )

        manifest = plan(
            [make_run(1, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)],
            subscriptions,
            "reopened",
        )

        assert manifest.is_safe is False
        assert "does not subscribe to 'reopened'" in (
            manifest.blocked[0].blocked_reason or ""
        )

    def test_clears_when_every_sharer_subscribes_to_the_recovery_event(
        self, tmp_path: Path
    ):
        subscriptions = self.load_pair(
            tmp_path, "[opened, reopened]", "[reopened, synchronize]"
        )

        manifest = plan(
            [make_run(1, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)],
            subscriptions,
            "reopened",
        )

        assert manifest.is_safe is True


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
