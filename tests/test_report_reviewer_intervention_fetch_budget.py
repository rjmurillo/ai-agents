"""The shared GraphQL budget stops further requests, never a read that has finished."""

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
LOW = fetch.MIN_REMAINING_POINTS - 1


def _limit(remaining: int, cost: int = 6) -> dict[str, int]:
    return {"cost": cost, "remaining": remaining}


def _follow_up(*, remaining: int, has_next: bool) -> dict[str, Any]:
    return {
        "rateLimit": _limit(remaining, 1),
        "repository": {
            "pullRequest": {
                "reviewThreads": {
                    "pageInfo": {
                        "hasNextPage": has_next,
                        "endCursor": "t2" if has_next else None,
                    },
                    "nodes": [make_thread("B")],
                }
            }
        },
    }


def _pr_needing_follow_up() -> dict[str, Any]:
    pr = make_pr(7, [make_thread("A")])
    pr["reviewThreads"]["pageInfo"] = {"hasNextPage": True, "endCursor": "t1"}
    return pr


def test_a_low_budget_stops_before_the_next_pull_request_page() -> None:
    page = make_page([make_pr(1, [])], "c1")
    page["rateLimit"] = _limit(LOW)
    gql = FakeGraphQL({None: page, "c1": make_page([make_pr(2, [])])})

    with pytest.raises(fetch.FetchError, match="budget low"):
        fetch.fetch_pull_requests(gql, "o", "r", SINCE)

    assert len(gql.calls) == 1


def test_a_low_budget_on_the_last_page_keeps_the_finished_read() -> None:
    page = make_page([make_pr(1, [])])
    page["rateLimit"] = _limit(LOW)

    prs, examined = fetch.fetch_pull_requests(FakeGraphQL({None: page}), "o", "r", SINCE)

    assert examined == 1
    assert [p["number"] for p in prs] == [1]


def test_a_low_budget_stops_before_a_thread_follow_up_is_issued() -> None:
    page = make_page([_pr_needing_follow_up()])
    page["rateLimit"] = _limit(LOW)
    gql = FakeGraphQL({None: page}, {(7, "t1"): _follow_up(remaining=LOW, has_next=False)})

    with pytest.raises(fetch.FetchError, match="budget low"):
        fetch.fetch_pull_requests(gql, "o", "r", SINCE)

    assert len(gql.calls) == 1


def test_a_low_budget_stops_before_the_next_thread_follow_up_page() -> None:
    page = make_page([_pr_needing_follow_up()])
    page["rateLimit"] = _limit(500)
    gql = FakeGraphQL({None: page}, {(7, "t1"): _follow_up(remaining=LOW, has_next=True)})

    with pytest.raises(fetch.FetchError, match="budget low"):
        fetch.fetch_pull_requests(gql, "o", "r", SINCE)

    assert len(gql.calls) == 2


def test_a_low_budget_on_the_last_thread_follow_up_keeps_the_finished_read() -> None:
    page = make_page([_pr_needing_follow_up()])
    page["rateLimit"] = _limit(500)
    gql = FakeGraphQL({None: page}, {(7, "t1"): _follow_up(remaining=LOW, has_next=False)})

    prs, _ = fetch.fetch_pull_requests(gql, "o", "r", SINCE)

    assert [t["id"] for t in prs[0]["threads"]] == ["A", "B"]


def test_a_budget_exactly_at_the_floor_continues() -> None:
    page = make_page([make_pr(1, [])], "c1")
    page["rateLimit"] = _limit(fetch.MIN_REMAINING_POINTS)
    gql = FakeGraphQL({None: page, "c1": make_page([make_pr(2, [])])})

    prs, _ = fetch.fetch_pull_requests(gql, "o", "r", SINCE)

    assert [p["number"] for p in prs] == [1, 2]


def test_a_response_without_a_rate_limit_block_cannot_trigger_the_stop() -> None:
    gql = FakeGraphQL({None: make_page([make_pr(1, [])], "c1"), "c1": make_page([])})

    prs, _ = fetch.fetch_pull_requests(gql, "o", "r", SINCE)

    assert [p["number"] for p in prs] == [1]
