"""Tests for run enumeration and cancellation (issue #4835).

Every case drives a fake client. Nothing here reaches the network, and the fake
records its calls so a test can assert what the guard would have done to the
live API.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import pytest

from scripts.github_core.workflow_runs import (
    PAGE_SIZE,
    JobsNotMaterializedError,
    cancel_runs,
    collect_runs_for_branches,
    iter_paginated,
    run_contexts,
)


class FakeClient:
    """Records reads and writes, answering from a canned response table."""

    def __init__(self, responses: dict[str, Any] | None = None):
        self.responses = responses or {}
        self.gets: list[str] = []
        self.posts: list[str] = []
        self.post_failures: dict[str, Exception] = {}

    def rest_get(self, endpoint: str) -> Any:
        self.gets.append(endpoint)
        if endpoint in self.responses:
            return self.responses[endpoint]
        return {}

    def rest_post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.posts.append(endpoint)
        failure = self.post_failures.get(endpoint)
        if failure is not None:
            raise failure
        return {}

    def rest_patch(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {}

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        return {}

    def is_authenticated(self) -> bool:
        return True


def page_url(endpoint: str, page: int) -> str:
    separator = "&" if "?" in endpoint else "?"
    return f"{endpoint}{separator}per_page={PAGE_SIZE}&page={page}"


def runs_url(repository: str, branch: str, status: str) -> str:
    """The branch-runs endpoint the module builds, with values percent-encoded.

    Spelled out here rather than reusing the module's private helpers so the
    encoding contract is asserted by the fixture rather than borrowed from the
    code under test.
    """
    return (
        f"repos/{quote(repository, safe='/')}/actions/runs"
        f"?branch={quote(branch, safe='')}&status={quote(status, safe='')}"
    )


class TestIterPaginated:
    def test_walks_every_full_page_and_stops_on_the_short_one(self):
        endpoint = "repos/o/r/actions/runs"
        first = [{"id": index} for index in range(PAGE_SIZE)]
        second = [{"id": 999}]
        client = FakeClient(
            {
                page_url(endpoint, 1): {"workflow_runs": first},
                page_url(endpoint, 2): {"workflow_runs": second},
            }
        )

        items = list(iter_paginated(client, endpoint, "workflow_runs"))

        assert len(items) == PAGE_SIZE + 1
        assert len(client.gets) == 2

    def test_stops_immediately_on_an_empty_first_page(self):
        endpoint = "repos/o/r/actions/runs"
        client = FakeClient({page_url(endpoint, 1): {"workflow_runs": []}})

        assert list(iter_paginated(client, endpoint, "workflow_runs")) == []
        assert len(client.gets) == 1

    def test_preserves_an_existing_query_string(self):
        endpoint = "repos/o/r/actions/runs?status=queued"
        client = FakeClient({page_url(endpoint, 1): {"workflow_runs": [{"id": 1}]}})

        list(iter_paginated(client, endpoint, "workflow_runs"))

        assert client.gets[0] == "repos/o/r/actions/runs?status=queued&per_page=100&page=1"

    def test_missing_key_is_treated_as_the_end_of_the_walk(self):
        client = FakeClient({page_url("e", 1): {"unexpected": [{"id": 1}]}})

        assert list(iter_paginated(client, "e", "workflow_runs")) == []

    def test_non_mapping_entries_are_skipped(self):
        client = FakeClient({page_url("e", 1): {"items": [{"id": 1}, "junk", None]}})

        assert list(iter_paginated(client, "e", "items")) == [{"id": 1}]


class TestRunContexts:
    def test_returns_job_names_as_check_contexts(self):
        endpoint = "repos/o/r/actions/runs/5/jobs"
        client = FakeClient(
            {page_url(endpoint, 1): {"jobs": [{"name": "Validate PR"}, {"name": "Lint"}]}}
        )

        assert run_contexts(client, "o/r", 5) == ("Validate PR", "Lint")

    def test_two_jobs_sharing_a_name_collapse_to_one_context(self):
        endpoint = "repos/o/r/actions/runs/5/jobs"
        client = FakeClient(
            {page_url(endpoint, 1): {"jobs": [{"name": "Same"}, {"name": "Same"}]}}
        )

        assert run_contexts(client, "o/r", 5) == ("Same",)

    def test_unnamed_job_is_skipped(self):
        endpoint = "repos/o/r/actions/runs/5/jobs"
        client = FakeClient(
            {page_url(endpoint, 1): {"jobs": [{"name": ""}, {"id": 3}, {"name": "Ok"}]}}
        )

        assert run_contexts(client, "o/r", 5) == ("Ok",)

    def test_zero_job_records_raises_instead_of_returning_verified_empty(self):
        """Issue #4835 gap: a run in this state is not evidence it publishes no
        required context. Every valid workflow declares at least one job, so
        zero records means GitHub has not materialized them yet (a queued
        run), not that the run has none. Callers must fail closed, not treat
        this the same as a resolved, verified empty context tuple.
        """
        endpoint = "repos/o/r/actions/runs/5/jobs"
        client = FakeClient({page_url(endpoint, 1): {"jobs": []}})

        with pytest.raises(JobsNotMaterializedError, match="run 5"):
            run_contexts(client, "o/r", 5)


class TestEndpointEncoding:
    """Interpolated values are percent-encoded before they reach the query.

    Git permits ``&`` and ``+`` in a refname. Interpolated raw, a branch named
    ``feat/a&status=completed`` appends a second ``status`` parameter, and the
    walk enumerates completed runs instead of the queued ones the operator is
    about to cancel: a wrong run set, silently.
    """

    HOSTILE_BRANCH = "feat/a&status=completed"

    def test_a_branch_carrying_a_query_separator_is_encoded(self):
        client = FakeClient()

        collect_runs_for_branches(
            client, "o/r", {self.HOSTILE_BRANCH: 1}, statuses=["queued"]
        )

        assert len(client.gets) == 1
        url = client.gets[0]
        assert "feat%2Fa%26status%3Dcompleted" in url
        assert url.count("status=") == 1
        assert "status=completed" not in url

    def test_the_encoded_url_is_the_one_the_fake_answers(self):
        """Control for the case above: the encoded URL is a real endpoint the
        module reads through, not merely a string it happens to build.
        """
        endpoint = runs_url("o/r", self.HOSTILE_BRANCH, "queued")
        client = FakeClient(
            {
                page_url(endpoint, 1): {
                    "workflow_runs": [
                        {"id": 31, "name": "W", "event": "synchronize",
                         "status": "queued"}
                    ]
                },
                page_url("repos/o/r/actions/runs/31/jobs", 1): {
                    "jobs": [{"name": "Validate PR"}]
                },
            }
        )

        runs = collect_runs_for_branches(
            client, "o/r", {self.HOSTILE_BRANCH: 1}, statuses=["queued"]
        )

        assert [run.run_id for run in runs] == [31]

    def test_a_repository_owner_keeps_its_path_separator(self):
        client = FakeClient()

        cancel_runs(client, "o/r", [5])

        assert client.posts == ["repos/o/r/actions/runs/5/cancel"]

    def test_a_repository_with_a_reserved_character_is_encoded_per_segment(self):
        client = FakeClient()

        run_contexts_endpoint_client = client
        with pytest.raises(JobsNotMaterializedError):
            run_contexts(run_contexts_endpoint_client, "o w/r?x", 5)

        assert client.gets[0].startswith("repos/o%20w/r%3Fx/actions/runs/5/jobs")


class TestCollectRunsForBranches:
    def _client(self) -> FakeClient:
        queued = runs_url("o/r", "feat/a", "queued")
        in_progress = runs_url("o/r", "feat/a", "in_progress")
        jobs_11 = "repos/o/r/actions/runs/11/jobs"
        jobs_12 = "repos/o/r/actions/runs/12/jobs"
        return FakeClient(
            {
                page_url(queued, 1): {
                    "workflow_runs": [
                        {"id": 11, "name": "Validate PR", "event": "synchronize",
                         "status": "queued"}
                    ]
                },
                page_url(in_progress, 1): {
                    "workflow_runs": [
                        {"id": 12, "name": "Run Python Tests", "event": "synchronize",
                         "status": "in_progress"}
                    ]
                },
                page_url(jobs_11, 1): {"jobs": [{"name": "Validate PR"}]},
                page_url(jobs_12, 1): {"jobs": [{"name": "Run Python Tests"}]},
            }
        )

    def test_collects_both_active_statuses_with_their_contexts(self):
        runs = collect_runs_for_branches(self._client(), "o/r", {"feat/a": 42})

        assert {run.run_id for run in runs} == {11, 12}
        assert all(run.pr_number == 42 for run in runs)
        assert all(run.branch == "feat/a" for run in runs)
        by_id = {run.run_id: run for run in runs}
        assert by_id[11].contexts == ("Validate PR",)
        assert by_id[11].jobs_verified is True
        assert by_id[12].status == "in_progress"

    def test_a_run_without_a_numeric_id_is_skipped(self):
        endpoint = runs_url("o/r", "feat/a", "queued")
        client = FakeClient(
            {page_url(endpoint, 1): {"workflow_runs": [{"name": "No id"}]}}
        )

        assert collect_runs_for_branches(client, "o/r", {"feat/a": 1}) == []

    def test_the_same_run_id_across_two_statuses_is_collected_once(self):
        queued = runs_url("o/r", "feat/a", "queued")
        in_progress = runs_url("o/r", "feat/a", "in_progress")
        payload = {"id": 11, "name": "W", "event": "synchronize", "status": "queued"}
        client = FakeClient(
            {
                page_url(queued, 1): {"workflow_runs": [payload]},
                page_url(in_progress, 1): {"workflow_runs": [payload]},
                page_url("repos/o/r/actions/runs/11/jobs", 1): {"jobs": []},
            }
        )

        runs = collect_runs_for_branches(client, "o/r", {"feat/a": 1})

        assert len(runs) == 1

    def test_an_unmaterialized_run_is_included_but_marked_unverified(self):
        """The exact scenario the AI-Spec-Validator flagged on PR #5357: a
        queued run whose jobs endpoint has not caught up yet must still show
        up in the inventory (so the operator sees it and its blast radius is
        counted), but with contexts=() and jobs_verified=False rather than
        silently resolving to a verified-safe empty context set.
        """
        endpoint = runs_url("o/r", "feat/a", "queued")
        client = FakeClient(
            {
                page_url(endpoint, 1): {
                    "workflow_runs": [
                        {"id": 21, "name": "Validate PR", "event": "synchronize",
                         "status": "queued"}
                    ]
                },
                page_url("repos/o/r/actions/runs/21/jobs", 1): {"jobs": []},
            }
        )

        runs = collect_runs_for_branches(client, "o/r", {"feat/a": 1}, statuses=["queued"])

        assert len(runs) == 1
        assert runs[0].contexts == ()
        assert runs[0].jobs_verified is False

    def test_explicit_status_list_narrows_the_walk(self):
        endpoint = runs_url("o/r", "feat/a", "queued")
        client = FakeClient({page_url(endpoint, 1): {"workflow_runs": []}})

        collect_runs_for_branches(client, "o/r", {"feat/a": 1}, statuses=["queued"])

        assert all("in_progress" not in url for url in client.gets)


class TestCancelRuns:
    def test_posts_one_cancel_per_run(self):
        client = FakeClient()

        outcome = cancel_runs(client, "o/r", [1, 2])

        assert outcome.cancelled == (1, 2)
        assert outcome.is_complete is True
        assert client.posts == [
            "repos/o/r/actions/runs/1/cancel",
            "repos/o/r/actions/runs/2/cancel",
        ]

    def test_a_failing_run_does_not_abort_the_remaining_ones(self):
        client = FakeClient()
        client.post_failures["repos/o/r/actions/runs/2/cancel"] = RuntimeError("409")

        outcome = cancel_runs(client, "o/r", [1, 2, 3])

        assert outcome.cancelled == (1, 3)
        assert outcome.failed == ((2, "409"),)
        assert outcome.is_complete is False

    def test_an_exception_with_no_message_still_records_a_reason(self):
        client = FakeClient()
        client.post_failures["repos/o/r/actions/runs/1/cancel"] = RuntimeError()

        outcome = cancel_runs(client, "o/r", [1])

        assert outcome.failed == ((1, "RuntimeError"),)

    def test_an_empty_run_list_is_a_complete_no_op(self):
        client = FakeClient()

        outcome = cancel_runs(client, "o/r", [])

        assert outcome.is_complete is True
        assert client.posts == []

    @pytest.mark.parametrize("failure", [OSError("net"), ValueError("bad json")])
    def test_transport_and_decode_failures_are_both_captured(self, failure: Exception):
        client = FakeClient()
        client.post_failures["repos/o/r/actions/runs/1/cancel"] = failure

        outcome = cancel_runs(client, "o/r", [1])

        assert outcome.failed[0][0] == 1
