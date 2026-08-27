"""Where a run's required-context set comes from (issue #4835).

Split out of ``tests/ci/test_recovery_manifest.py`` when that file crossed the
500-line taste ceiling. Every case here is about one question the planner has to
answer before it can gate anything: which required contexts would this
cancellation remove, and can the named event bring them back. The gating
behavior built on those answers stays in the original module.
"""

from __future__ import annotations

from scripts.github_core.recovery_manifest import WorkflowRun, manifest_to_dict
from scripts.github_core.workflow_event_subscriptions import (
    parse_workflow_subscriptions,
)
from tests.ci.bulk_cancel_fixtures import (
    REQUIRED_CONTEXT,
    REQUIRED_WORKFLOW,
    SECOND_REQUIRED_CONTEXT,
    SECOND_REQUIRED_WORKFLOW,
    healthy_subscriptions,
    make_run,
    reopened_omitting_subscriptions,
    subscriptions_with,
    workflow_document,
)
from tests.ci.bulk_cancel_fixtures import (
    plan_with_pinned_contract as plan,
)


def queued_run_with_no_api_contexts(workflow: str = SECOND_REQUIRED_WORKFLOW):
    """A queued run whose jobs endpoint answered with nothing usable.

    This is the shape the live ``--all-open-prs`` path produces for a run whose
    required job sits behind ``needs:``: GitHub has materialized no job record
    yet, so ``run_contexts`` resolves to an empty tuple even though the run will
    publish a required context once the gate ahead of it finishes.
    """
    return WorkflowRun(
        run_id=1,
        workflow_name=workflow,
        pr_number=7,
        branch="feat/queued",
        event="synchronize",
        status="queued",
        contexts=(),
    )


class TestStaticallyDeclaredJobNames:
    """The workflow file, not the jobs API, decides what a run publishes.

    ``run_contexts`` reads only job records GitHub has already materialized. A
    ``needs:``-gated job has none while the run is queued, so a run that will
    publish ``Run Python Tests`` reports zero contexts and ``_classify`` cleared
    it for unguarded cancellation. Seven of the nine contexts in
    ``ruleset_required_contexts.py`` resolve to gated jobs, so this is the
    common case rather than an edge.
    """

    def _subscriptions(self, jobs: dict[str, object]):
        return {
            SECOND_REQUIRED_WORKFLOW: parse_workflow_subscriptions(
                workflow_document(
                    SECOND_REQUIRED_WORKFLOW,
                    ["opened", "synchronize", "reopened"],
                    jobs=jobs,
                )
            )
        }

    def test_negative_control_clears_when_the_workflow_declares_no_such_job(self):
        """Without the job declaration the same run still clears, which is what
        the code did for every run before the static union existed. Pairing it
        with the case below makes the block attributable to the declaration.
        """
        subscriptions = self._subscriptions({"lint": {"name": "Lint"}})

        manifest = plan([queued_run_with_no_api_contexts()], subscriptions, None)

        assert manifest.is_safe is True

    def test_queued_run_blocks_on_a_job_name_the_workflow_declares(self):
        subscriptions = self._subscriptions(
            {"tests": {"name": SECOND_REQUIRED_CONTEXT, "needs": ["setup"]}}
        )

        manifest = plan([queued_run_with_no_api_contexts()], subscriptions, None)

        assert manifest.is_safe is False
        entry = manifest.blocked[0]
        assert entry.required_contexts == (SECOND_REQUIRED_CONTEXT,)
        assert "no recovery event was named" in (entry.blocked_reason or "")

    def test_a_matrix_job_name_matches_by_its_literal_prefix(self):
        """``codeql-analysis.yml`` declares one job named
        ``Analyze (${{ matrix.language }})`` and branch protection requires the
        two expanded names, so only the prefix is knowable statically.
        """
        subscriptions = {
            "CodeQL Analysis": parse_workflow_subscriptions(
                workflow_document(
                    "CodeQL Analysis",
                    ["opened", "synchronize", "reopened"],
                    jobs={"analyze": {"name": "Analyze (${{ matrix.language }})"}},
                )
            )
        }

        manifest = plan(
            [queued_run_with_no_api_contexts("CodeQL Analysis")], subscriptions, None
        )

        assert manifest.is_safe is False
        assert manifest.blocked[0].required_contexts == (
            "Analyze (actions)",
            "Analyze (python)",
        )

    def test_a_literal_job_name_does_not_claim_a_longer_required_context(self):
        """``Validate PR`` and ``Validate PR title`` are two required contexts
        from two workflows. Prefix matching a literal name would let the first
        job claim the second, inflating every manifest with contexts the
        workflow cannot publish.
        """
        subscriptions = {
            "PR Validation": parse_workflow_subscriptions(
                workflow_document(
                    "PR Validation",
                    ["opened", "synchronize", "reopened"],
                    jobs={"validate": {"name": "Validate PR"}},
                )
            )
        }

        manifest = plan(
            [queued_run_with_no_api_contexts("PR Validation")], subscriptions, "reopened"
        )

        assert manifest.entries[0].required_contexts == ("Validate PR",)


class TestUnknownWorkflowFailsClosed:
    """An unresolvable workflow name is an unread question, not an empty answer.

    Before this guard a run whose workflow file the loader never saw, deleted,
    renamed, or living outside ``--workflows-dir``, arrived with an empty
    context tuple and verified as "publishes nothing required".
    """

    def test_a_run_whose_workflow_is_absent_from_the_corpus_blocks(self):
        manifest = plan([queued_run_with_no_api_contexts()], {}, None)

        assert manifest.is_safe is False
        assert "published contexts cannot be determined" in (
            manifest.blocked[0].blocked_reason or ""
        )

    def test_control_the_same_run_clears_once_its_workflow_resolves(self):
        subscriptions = subscriptions_with(
            {SECOND_REQUIRED_WORKFLOW: ["opened", "synchronize", "reopened"]}
        )

        manifest = plan([queued_run_with_no_api_contexts()], subscriptions, None)

        assert manifest.is_safe is True


class TestTriggerPathFilters:
    """A path-filtered workflow declaring ``reopened`` still may not come back.

    Reopening a PR whose diff touches none of the filtered paths produces no run
    for that workflow, so the declared subscription is necessary but not
    sufficient. Six workflow files in ``.github/workflows`` carry ``paths`` on a
    pull_request-family trigger today; none publishes a required context yet,
    and nothing stops one from doing so.
    """

    def _subscriptions(self, paths: list[str] | None):
        return {
            REQUIRED_WORKFLOW: parse_workflow_subscriptions(
                workflow_document(
                    REQUIRED_WORKFLOW,
                    ["opened", "synchronize", "reopened"],
                    paths=paths,
                )
            )
        }

    def test_path_filtered_workflow_blocks_a_required_run(self):
        manifest = plan(
            [make_run(1, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)],
            self._subscriptions(["docs/**"]),
            "reopened",
        )

        assert manifest.is_safe is False
        reason = manifest.blocked[0].blocked_reason or ""
        assert "declares pull_request trigger path filters" in reason

    def test_control_the_same_workflow_without_paths_verifies(self):
        manifest = plan(
            [make_run(1, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)],
            self._subscriptions(None),
            "reopened",
        )

        assert manifest.is_safe is True

    def test_a_base_branch_filter_alone_does_not_block(self):
        """``branches:`` filters the pull request's base ref, which does not
        move on close/reopen or resynchronize, so a run that exists at all
        already satisfies it. 33 of this repository's workflow files declare it
        on ``pull_request``; blocking on it would refuse every batch.
        """
        subscriptions = {
            REQUIRED_WORKFLOW: parse_workflow_subscriptions(
                {
                    "name": REQUIRED_WORKFLOW,
                    "on": {
                        "pull_request": {
                            "types": ["opened", "synchronize", "reopened"],
                            "branches": ["main"],
                        }
                    },
                }
            )
        }

        manifest = plan(
            [make_run(1, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)],
            subscriptions,
            "reopened",
        )

        assert manifest.is_safe is True


class TestVerificationProvenance:
    """``verified: true`` must say what was checked to reach it."""

    def _run(self):
        return make_run(1, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)

    def test_rerun_records_that_no_subscription_was_checked(self):
        manifest = plan(
            [self._run()], subscriptions_with({REQUIRED_WORKFLOW: []}), "rerun"
        )

        entry = manifest.entries[0]
        assert entry.verified is True
        assert entry.verification == "rerun"
        assert manifest_to_dict(manifest)["entries"][0]["verification"] == "rerun"

    def test_a_trigger_backed_event_records_the_subscription_check(self):
        manifest = plan([self._run()], healthy_subscriptions(), "reopened")

        assert manifest.entries[0].verification == "subscription"

    def test_a_blocked_entry_records_that_nothing_verified(self):
        manifest = plan([self._run()], reopened_omitting_subscriptions(), "reopened")

        assert manifest.blocked[0].verification == "none"

    def test_the_run_id_is_the_rerun_handle_the_manifest_records(self):
        """``rerun`` skips the subscription check, so the only thing that makes
        the plan actionable is the run id the operator feeds back to the Actions
        API. Losing it would leave a verified entry nobody can act on.
        """
        manifest = plan(
            [self._run()], subscriptions_with({REQUIRED_WORKFLOW: []}), "rerun"
        )

        assert manifest_to_dict(manifest)["entries"][0]["run_id"] == 1

