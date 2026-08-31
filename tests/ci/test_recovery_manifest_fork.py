"""Fork recovery blocking tests for the bulk cancellation guard (issue #4835).

Split from test_recovery_manifest.py to stay under the 500-line ceiling.
"""

from __future__ import annotations

from tests.ci.bulk_cancel_fixtures import (
    OPTIONAL_WORKFLOW,
    REQUIRED_CONTEXT,
    REQUIRED_WORKFLOW,
    healthy_subscriptions,
    make_run,
)
from tests.ci.bulk_cancel_fixtures import (
    plan_with_pinned_contract as plan,
)


class TestForkRecoveryBlocking:
    """A fork PR's head ref is not dispatchable in the base repository.

    workflow_dispatch requires a ref that exists in the repository that owns
    the workflow. A fork PR's head branch lives only in the fork, so
    dispatching against it fails. The planner must refuse dispatch recovery
    for fork-only runs while still allowing rerun and pull_request events.
    """

    @staticmethod
    def _dispatch_subscriptions():
        """Subscriptions where every workflow has both PR and dispatch triggers."""
        from scripts.github_core.workflow_event_subscriptions import (
            parse_workflow_subscriptions,
        )

        def _doc(name, pr_types):
            return {
                "name": name,
                "on": {
                    "pull_request": {"types": pr_types},
                    "workflow_dispatch": {},
                },
                "jobs": {},
            }

        return {
            name: parse_workflow_subscriptions(
                _doc(name, ["opened", "synchronize", "reopened"])
            )
            for name in [REQUIRED_WORKFLOW, OPTIONAL_WORKFLOW]
        }

    def test_dispatch_recovery_blocks_for_fork_run(self):
        run = make_run(
            1,
            workflow=REQUIRED_WORKFLOW,
            context=REQUIRED_CONTEXT,
            head_repo="contributor/ai-agents",
        )
        manifest = plan(
            [run], self._dispatch_subscriptions(), "workflow_dispatch"
        )

        assert manifest.is_safe is False
        assert "fork" in manifest.entries[0].blocked_reason.lower()
        assert "not dispatchable" in manifest.entries[0].blocked_reason

    def test_rerun_recovery_is_unaffected_by_fork_origin(self):
        run = make_run(
            1,
            workflow=REQUIRED_WORKFLOW,
            context=REQUIRED_CONTEXT,
            head_repo="contributor/ai-agents",
        )
        manifest = plan([run], healthy_subscriptions(), "rerun")

        assert manifest.is_safe is True

    def test_synchronize_recovery_is_unaffected_by_fork_origin(self):
        run = make_run(
            1,
            workflow=REQUIRED_WORKFLOW,
            context=REQUIRED_CONTEXT,
            head_repo="contributor/ai-agents",
        )
        manifest = plan([run], healthy_subscriptions(), "synchronize")

        assert manifest.is_safe is True

    def test_same_repo_dispatch_recovery_is_not_blocked(self):
        run = make_run(
            1,
            workflow=REQUIRED_WORKFLOW,
            context=REQUIRED_CONTEXT,
            head_repo="rjmurillo/ai-agents",
        )
        manifest = plan(
            [run], self._dispatch_subscriptions(), "workflow_dispatch"
        )

        assert manifest.is_safe is True

    def test_empty_head_repo_blocks_dispatch_fail_closed(self):
        """Unknown repository identity must fail closed for workflow_dispatch."""
        run = make_run(
            1,
            workflow=REQUIRED_WORKFLOW,
            context=REQUIRED_CONTEXT,
            head_repo="",
        )
        manifest = plan(
            [run], self._dispatch_subscriptions(), "workflow_dispatch"
        )

        assert manifest.is_safe is False
        assert "unknown" in manifest.entries[0].blocked_reason.lower()

    def test_case_insensitive_repo_comparison(self):
        run = make_run(
            1,
            workflow=REQUIRED_WORKFLOW,
            context=REQUIRED_CONTEXT,
            head_repo="RJMurillo/AI-Agents",
        )
        manifest = plan(
            [run], self._dispatch_subscriptions(), "workflow_dispatch"
        )

        assert manifest.is_safe is True


class TestForkIdentityRoundTrip:
    """head_repo survives serialization and manifest replay."""

    def test_head_repo_appears_in_serialized_manifest(self):
        from scripts.github_core.recovery_manifest import manifest_to_dict

        run = make_run(
            1,
            workflow=REQUIRED_WORKFLOW,
            context=REQUIRED_CONTEXT,
            head_repo="contributor/ai-agents",
        )
        manifest = plan([run], healthy_subscriptions(), "rerun")
        serialized = manifest_to_dict(manifest)

        assert serialized["entries"][0]["head_repo"] == "contributor/ai-agents"

    def test_head_repo_survives_manifest_round_trip(self):
        from scripts.github_core.recovery_manifest import manifest_to_dict
        from scripts.github_core.runs_file import run_from_manifest_entry

        run = make_run(
            1,
            workflow=REQUIRED_WORKFLOW,
            context=REQUIRED_CONTEXT,
            head_repo="contributor/ai-agents",
        )
        manifest = plan([run], healthy_subscriptions(), "rerun")
        serialized = manifest_to_dict(manifest)
        restored = run_from_manifest_entry(serialized["entries"][0])

        assert restored.head_repo == "contributor/ai-agents"

    def test_same_repo_head_repo_round_trips(self):
        from scripts.github_core.recovery_manifest import manifest_to_dict
        from scripts.github_core.runs_file import run_from_manifest_entry

        run = make_run(
            1,
            workflow=REQUIRED_WORKFLOW,
            context=REQUIRED_CONTEXT,
            head_repo="rjmurillo/ai-agents",
        )
        manifest = plan([run], healthy_subscriptions(), "rerun")
        serialized = manifest_to_dict(manifest)
        restored = run_from_manifest_entry(serialized["entries"][0])

        assert restored.head_repo == "rjmurillo/ai-agents"
