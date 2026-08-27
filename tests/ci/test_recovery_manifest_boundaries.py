"""Copilot review fixes for the recovery planner's two boundaries (PR #5357).

Two findings, both about a guard that refuses more or less than it should:

- The pull_request ``paths:`` filter was rejecting ``rerun`` and
  ``workflow_dispatch``, neither of which evaluates that filter, so two of the
  four advertised recovery modes were unusable for every path-filtered
  workflow. ``TestPathFilterScope``.
- ``run_from_mapping`` documented a ``list[str]`` contract and accepted any
  iterable, stringifying each item, and read ``jobs_verified`` through
  ``bool()`` so the string ``"false"`` became ``True``.
  ``TestBoundaryTypesAreValidatedNotCoerced``.

Split out of ``tests/ci/test_recovery_manifest.py`` because that file was
already within 90 lines of the 500-line taste ceiling.
"""

from __future__ import annotations

import pytest

from scripts.github_core.recovery_manifest import run_from_mapping
from scripts.github_core.workflow_event_subscriptions import (
    parse_workflow_subscriptions,
)
from tests.ci.bulk_cancel_fixtures import (
    REQUIRED_CONTEXT,
    REQUIRED_WORKFLOW,
    make_run,
)
from tests.ci.bulk_cancel_fixtures import (
    plan_with_pinned_contract as plan,
)


class TestPathFilterScope:
    """A pull_request path filter blocks only the events it can suppress.

    ``has_path_filters`` is read from the pull_request-family triggers alone.
    ``rerun`` re-executes the run through the Actions API and
    ``workflow_dispatch`` fires a trigger that has no path filters, so neither
    consults the pull_request ``paths:`` list. Rejecting them on it refused two
    of the four advertised recovery modes for every path-filtered workflow.
    """

    def _subscriptions(self) -> dict:
        document = {
            "name": REQUIRED_WORKFLOW,
            "on": {
                "pull_request": {
                    "types": ["opened", "synchronize", "reopened"],
                    "paths": ["docs/**"],
                },
                "workflow_dispatch": None,
            },
            "jobs": {},
        }
        return {REQUIRED_WORKFLOW: parse_workflow_subscriptions(document)}

    def _plan(self, recovery_event: str):
        return plan(
            [make_run(1, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)],
            self._subscriptions(),
            recovery_event,
        )

    @pytest.mark.parametrize("event", ["synchronize", "reopened"])
    def test_a_pull_request_event_is_still_blocked_by_a_path_filter(self, event: str):
        manifest = self._plan(event)

        assert manifest.is_safe is False
        assert "path filters" in (manifest.entries[0].blocked_reason or "")

    @pytest.mark.parametrize("event", ["rerun", "workflow_dispatch"])
    def test_a_non_pull_request_event_is_not_blocked_by_a_path_filter(self, event: str):
        manifest = self._plan(event)

        assert manifest.is_safe is True
        assert manifest.entries[0].blocked_reason is None

    def test_an_unsubscribed_dispatch_still_blocks_under_a_path_filter(self):
        """Control: relaxing the path-filter guard must not relax the
        subscription check that sits above it. A workflow that declares path
        filters and no ``workflow_dispatch`` trigger still blocks.
        """
        document = {
            "name": REQUIRED_WORKFLOW,
            "on": {"pull_request": {"types": ["opened"], "paths": ["docs/**"]}},
            "jobs": {},
        }
        manifest = plan(
            [make_run(1, workflow=REQUIRED_WORKFLOW, context=REQUIRED_CONTEXT)],
            {REQUIRED_WORKFLOW: parse_workflow_subscriptions(document)},
            "workflow_dispatch",
        )

        assert manifest.is_safe is False
        assert "does not subscribe" in (manifest.entries[0].blocked_reason or "")


class TestBoundaryTypesAreValidatedNotCoerced:
    """The captured-record boundary validates; it never converts.

    Coercion at this boundary fails open in both fields. Stringifying an
    arbitrary iterable turns a nested object into its key names and an integer
    into ``"7"``, none of which any ruleset requires, so the run reads as
    publishing nothing required and is cancelled with no recovery event. And
    ``bool("false")`` is ``True``, so an unmaterialized run recorded with a
    string ``"false"`` replays as trusted, which is the very fail-open state
    ``jobs_verified`` was added to close.
    """

    def record(self, **overrides: object) -> dict:
        base = {
            "run_id": 1,
            "workflow_name": REQUIRED_WORKFLOW,
            "pr_number": 7,
            "branch": "feat/x",
            "event": "synchronize",
            "status": "queued",
            "contexts": [REQUIRED_CONTEXT],
        }
        base.update(overrides)
        return base

    @pytest.mark.parametrize(
        "contexts",
        [
            {"Validate PR": True},
            ("Validate PR",),
            7,
            None,
        ],
    )
    def test_a_non_list_contexts_value_raises(self, contexts: object):
        with pytest.raises(ValueError, match="contexts must be a JSON list"):
            run_from_mapping(self.record(contexts=contexts))

    @pytest.mark.parametrize("item", [7, None, True, ["Validate PR"]])
    def test_a_non_string_context_item_raises(self, item: object):
        with pytest.raises(ValueError, match="contexts must hold only strings"):
            run_from_mapping(self.record(contexts=[item]))

    @pytest.mark.parametrize("value", ["false", "true", 0, 1, "", []])
    def test_a_non_boolean_jobs_verified_raises(self, value: object):
        with pytest.raises(ValueError, match="jobs_verified must be a JSON boolean"):
            run_from_mapping(self.record(jobs_verified=value))

    @pytest.mark.parametrize("value", [True, False])
    def test_a_real_json_boolean_is_honored(self, value: bool):
        assert run_from_mapping(self.record(jobs_verified=value)).jobs_verified is value

    def test_an_absent_jobs_verified_keeps_the_documented_default(self):
        assert run_from_mapping(self.record()).jobs_verified is True

    def test_a_string_false_can_no_longer_clear_an_unmaterialized_run(self):
        """End-to-end proof of the fail-open this closes.

        Before the fix, ``jobs_verified: "false"`` coerced to ``True``, so a
        replayed manifest for an unmaterialized run reached ``_classify`` as
        trusted and the whole batch planned as safe. Now the record is refused
        before it can reach the planner at all.
        """
        with pytest.raises(ValueError, match="jobs_verified must be a JSON boolean"):
            run_from_mapping(self.record(contexts=[], jobs_verified="false"))


