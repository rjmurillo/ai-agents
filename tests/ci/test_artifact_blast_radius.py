"""Artifact count in the bulk cancellation blast radius (issue #5365).

Requirement 6 of issue #4835 asks the guard to report artifact blast radius
before it mutates anything. The count costs one REST call per run, so the CLI
gates it behind ``--report-artifacts``. These cases pin the unit pieces: the
per-run read, the batch wrapper, the radius total, and the manifest shape.
"""

from __future__ import annotations

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS
from scripts.github_core.recovery_manifest import (
    manifest_to_dict,
    plan_recovery,
    summarize_blast_radius,
)
from scripts.github_core.workflow_runs import (
    PAGE_SIZE,
    iter_paginated,
    run_artifact_count,
    run_artifact_tally,
    with_artifact_counts,
)
from tests.ci.bulk_cancel_fixtures import healthy_subscriptions, make_run
from tests.ci.workflow_runs_fixtures import FakeClient, page_url

REPOSITORY = "o/r"


def artifacts_endpoint(run_id: int) -> str:
    return f"repos/{REPOSITORY}/actions/runs/{run_id}/artifacts"


def artifact_page(count: int, *, expired: int = 0) -> dict:
    live = [{"id": n, "name": f"a{n}", "expired": False} for n in range(count)]
    dead = [{"id": 1000 + n, "name": f"x{n}", "expired": True} for n in range(expired)]
    return {"total_count": count + expired, "artifacts": live + dead}


class TestRunArtifactCount:
    def test_counts_the_artifacts_on_one_page(self):
        client = FakeClient({page_url(artifacts_endpoint(7), 1): artifact_page(3)})

        assert run_artifact_count(client, REPOSITORY, 7) == 3
        assert client.gets == [page_url(artifacts_endpoint(7), 1)]

    def test_a_run_with_no_artifacts_counts_zero(self):
        client = FakeClient({page_url(artifacts_endpoint(7), 1): {"artifacts": []}})

        assert run_artifact_count(client, REPOSITORY, 7) == 0

    def test_an_unanswered_endpoint_counts_zero(self):
        assert run_artifact_count(FakeClient(), REPOSITORY, 7) == 0

    def test_expired_artifacts_are_not_counted(self):
        client = FakeClient({page_url(artifacts_endpoint(7), 1): artifact_page(2, expired=5)})

        assert run_artifact_count(client, REPOSITORY, 7) == 2

    def test_pages_are_walked_until_a_short_page(self):
        client = FakeClient(
            {
                page_url(artifacts_endpoint(7), 1): artifact_page(PAGE_SIZE),
                page_url(artifacts_endpoint(7), 2): artifact_page(4),
            }
        )

        assert run_artifact_count(client, REPOSITORY, 7) == PAGE_SIZE + 4
        assert len(client.gets) == 2

    def test_a_missing_expired_field_counts_as_live(self):
        payload = {"artifacts": [{"id": 1, "name": "a"}]}
        client = FakeClient({page_url(artifacts_endpoint(7), 1): payload})

        assert run_artifact_count(client, REPOSITORY, 7) == 1


class TestWithArtifactCounts:
    def test_makes_one_call_per_run_and_stamps_each_count(self):
        client = FakeClient(
            {
                page_url(artifacts_endpoint(1), 1): artifact_page(2),
                page_url(artifacts_endpoint(2), 1): artifact_page(0),
                page_url(artifacts_endpoint(3), 1): artifact_page(5),
            }
        )
        runs = [make_run(1), make_run(2), make_run(3)]

        counted = with_artifact_counts(client, REPOSITORY, runs)

        assert [run.artifact_count for run in counted] == [2, 0, 5]
        assert len(client.gets) == len(runs)

    def test_a_repeated_run_id_is_measured_once(self):
        client = FakeClient({page_url(artifacts_endpoint(1), 1): artifact_page(2)})

        counted = with_artifact_counts(client, REPOSITORY, [make_run(1), make_run(1)])

        assert [run.artifact_count for run in counted] == [2, 2]
        assert len(client.gets) == 1

    def test_no_runs_make_no_calls(self):
        client = FakeClient()

        assert with_artifact_counts(client, REPOSITORY, []) == []
        assert client.gets == []

    def test_other_fields_survive_and_the_input_is_unchanged(self):
        original = make_run(1, pr_number=9, branch="feat/x")
        client = FakeClient({page_url(artifacts_endpoint(1), 1): artifact_page(1)})

        (counted,) = with_artifact_counts(client, REPOSITORY, [original])

        assert original.artifact_count is None
        assert (counted.run_id, counted.pr_number, counted.branch) == (1, 9, "feat/x")


class TestBlastRadiusArtifacts:
    def test_unmeasured_runs_leave_the_count_unset(self):
        radius = summarize_blast_radius([make_run(1), make_run(2)], REQUIRED_CONTEXTS)

        assert radius.artifact_count is None

    def test_measured_runs_sum_their_counts(self):
        runs = [make_run(1), make_run(2)]
        client = FakeClient(
            {
                page_url(artifacts_endpoint(1), 1): artifact_page(2),
                page_url(artifacts_endpoint(2), 1): artifact_page(3),
            }
        )

        radius = summarize_blast_radius(
            with_artifact_counts(client, REPOSITORY, runs), REQUIRED_CONTEXTS
        )

        assert radius.artifact_count == 5

    def test_a_measured_zero_is_zero_not_unset(self):
        client = FakeClient({page_url(artifacts_endpoint(1), 1): artifact_page(0)})
        runs = with_artifact_counts(client, REPOSITORY, [make_run(1)])

        assert summarize_blast_radius(runs, REQUIRED_CONTEXTS).artifact_count == 0

    def test_a_partly_measured_inventory_leaves_the_count_unset(self):
        client = FakeClient({page_url(artifacts_endpoint(1), 1): artifact_page(4)})
        measured = with_artifact_counts(client, REPOSITORY, [make_run(1)])

        radius = summarize_blast_radius([*measured, make_run(2)], REQUIRED_CONTEXTS)

        assert radius.artifact_count is None

    def test_an_empty_inventory_leaves_the_count_unset(self):
        assert summarize_blast_radius([], REQUIRED_CONTEXTS).artifact_count is None


class TestManifestArtifacts:
    def _manifest(self, runs):
        return plan_recovery(
            runs,
            required=REQUIRED_CONTEXTS,
            subscriptions=healthy_subscriptions(),
            recovery_event="reopened",
            repository="rjmurillo/ai-agents",
        )

    def test_the_default_manifest_has_no_artifacts_key(self):
        payload = manifest_to_dict(self._manifest([make_run(1)]))

        assert "artifacts" not in payload["blast_radius"]

    def test_a_measured_manifest_records_the_total(self):
        client = FakeClient({page_url(artifacts_endpoint(1), 1): artifact_page(6)})
        runs = with_artifact_counts(client, REPOSITORY, [make_run(1)])

        payload = manifest_to_dict(self._manifest(runs))

        assert payload["blast_radius"]["artifacts"] == 6


class TestPageCapTruncation:
    """The page cap must be reported, not silently treated as a complete count (#6506)."""

    def _capped_client(self, monkeypatch, *, pages: int = 2):
        monkeypatch.setattr("scripts.github_core.workflow_runs._MAX_PAGES", pages)
        return FakeClient(
            {
                page_url(artifacts_endpoint(7), n): artifact_page(PAGE_SIZE)
                for n in range(1, pages + 2)
            }
        )

    def test_full_pages_to_the_cap_report_truncation(self, monkeypatch):
        client = self._capped_client(monkeypatch)

        count, truncated = run_artifact_tally(client, REPOSITORY, 7)

        assert truncated is True
        assert count == 2 * PAGE_SIZE
        assert len(client.gets) == 2

    def test_a_short_page_before_the_cap_is_not_truncated(self, monkeypatch):
        monkeypatch.setattr("scripts.github_core.workflow_runs._MAX_PAGES", 3)
        client = FakeClient(
            {
                page_url(artifacts_endpoint(7), 1): artifact_page(PAGE_SIZE),
                page_url(artifacts_endpoint(7), 2): artifact_page(4),
            }
        )

        assert run_artifact_tally(client, REPOSITORY, 7) == (PAGE_SIZE + 4, False)

    def test_a_short_page_at_the_cap_is_not_truncated(self, monkeypatch):
        monkeypatch.setattr("scripts.github_core.workflow_runs._MAX_PAGES", 2)
        client = FakeClient(
            {
                page_url(artifacts_endpoint(7), 1): artifact_page(PAGE_SIZE),
                page_url(artifacts_endpoint(7), 2): artifact_page(PAGE_SIZE - 1),
            }
        )

        assert run_artifact_tally(client, REPOSITORY, 7)[1] is False

    def test_iter_paginated_without_state_still_works_at_the_cap(self, monkeypatch):
        client = self._capped_client(monkeypatch)

        items = list(iter_paginated(client, artifacts_endpoint(7), "artifacts"))

        assert len(items) == 2 * PAGE_SIZE

    def test_with_artifact_counts_stamps_the_flag_and_the_radius_carries_it(self, monkeypatch):
        client = self._capped_client(monkeypatch)

        runs = with_artifact_counts(client, REPOSITORY, [make_run(7)])
        radius = summarize_blast_radius(runs, REQUIRED_CONTEXTS)

        assert runs[0].artifact_count_truncated is True
        assert radius.artifact_count_truncated is True

    def test_an_untruncated_radius_is_not_flagged(self):
        client = FakeClient({page_url(artifacts_endpoint(1), 1): artifact_page(2)})
        runs = with_artifact_counts(client, REPOSITORY, [make_run(1)])

        assert summarize_blast_radius(runs, REQUIRED_CONTEXTS).artifact_count_truncated is False

    def test_the_manifest_surfaces_truncation(self, monkeypatch):
        client = self._capped_client(monkeypatch)
        runs = with_artifact_counts(client, REPOSITORY, [make_run(7)])
        manifest = plan_recovery(
            runs,
            required=REQUIRED_CONTEXTS,
            subscriptions=healthy_subscriptions(),
            recovery_event="reopened",
            repository="rjmurillo/ai-agents",
        )

        blast = manifest_to_dict(manifest)["blast_radius"]

        assert blast["artifacts"] == 2 * PAGE_SIZE
        assert blast["artifacts_truncated"] is True

    def test_the_manifest_omits_the_flag_when_complete(self):
        client = FakeClient({page_url(artifacts_endpoint(1), 1): artifact_page(2)})
        runs = with_artifact_counts(client, REPOSITORY, [make_run(1)])
        manifest = plan_recovery(
            runs,
            required=REQUIRED_CONTEXTS,
            subscriptions=healthy_subscriptions(),
            recovery_event="reopened",
            repository="rjmurillo/ai-agents",
        )

        assert "artifacts_truncated" not in manifest_to_dict(manifest)["blast_radius"]
