"""A pagination flag the API leaves out or mistypes must fail loud, never end a read."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from scripts import reviewer_intervention_fetch as fetch
from tests.report_reviewer_intervention_helpers import (
    NOW,
    FakeGraphQL,
    make_page,
    make_pr,
    make_thread,
)

SINCE = NOW - timedelta(days=90)
BAD_FLAGS: list[Any] = [None, "false", "true", 0, 1, [], {}]


def _drop(info: dict[str, Any]) -> None:
    del info["hasNextPage"]


@pytest.mark.parametrize("flag", BAD_FLAGS)
def test_a_pr_page_with_a_non_boolean_flag_fails_loud(flag: Any) -> None:
    page = make_page([make_pr(1, [])])
    page["repository"]["pullRequests"]["pageInfo"]["hasNextPage"] = flag

    with pytest.raises(fetch.FetchError, match="missing pagination flag for pull requests"):
        fetch.fetch_pull_requests(FakeGraphQL({None: page}), "o", "r", SINCE)


def test_a_pr_page_without_the_flag_fails_loud() -> None:
    page = make_page([make_pr(1, [])])
    _drop(page["repository"]["pullRequests"]["pageInfo"])

    with pytest.raises(fetch.FetchError, match="missing pagination flag"):
        fetch.fetch_pull_requests(FakeGraphQL({None: page}), "o", "r", SINCE)


@pytest.mark.parametrize("flag", BAD_FLAGS)
def test_a_thread_connection_with_a_non_boolean_flag_fails_loud(flag: Any) -> None:
    pr = make_pr(7, [make_thread("A")])
    pr["reviewThreads"]["pageInfo"] = {"hasNextPage": flag, "endCursor": None}

    with pytest.raises(fetch.FetchError, match="missing pagination flag for PR #7 threads"):
        fetch.fetch_pull_requests(FakeGraphQL({None: make_page([pr])}), "o", "r", SINCE)


def test_a_thread_follow_up_page_without_the_flag_fails_loud() -> None:
    pr = make_pr(7, [make_thread("A")])
    pr["reviewThreads"]["pageInfo"] = {"hasNextPage": True, "endCursor": "t1"}
    follow_up = {
        "repository": {
            "pullRequest": {"reviewThreads": {"pageInfo": {"endCursor": None}, "nodes": []}}
        }
    }
    gql = FakeGraphQL({None: make_page([pr])}, {(7, "t1"): follow_up})

    with pytest.raises(fetch.FetchError, match="missing pagination flag"):
        fetch.fetch_pull_requests(gql, "o", "r", SINCE)


def test_a_real_boolean_false_still_ends_the_read() -> None:
    prs, examined = fetch.fetch_pull_requests(
        FakeGraphQL({None: make_page([make_pr(1, [])])}), "o", "r", SINCE
    )

    assert examined == 1
    assert [p["number"] for p in prs] == [1]
