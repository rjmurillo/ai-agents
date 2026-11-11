"""Tests for the pull request and thread fetch in report_reviewer_intervention_clusters.py."""

from __future__ import annotations

from datetime import timedelta

import pytest

from scripts import report_reviewer_intervention_clusters as rep
from tests.report_reviewer_intervention_helpers import (
    HUMAN,
    NOW,
    TRAILER_BODY,
    FakeGraphQL,
    make_page,
    make_pr,
    make_thread,
    three_repeat_pages,
)


def test_fetch_follows_every_pr_page_until_no_next_page() -> None:
    gql = FakeGraphQL(
        {
            None: make_page([make_pr(1, [])], "c1"),
            "c1": make_page([make_pr(2, [])], "c2"),
            "c2": make_page([make_pr(3, [])]),
        }
    )

    prs, examined = rep.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))

    assert [p["number"] for p in prs] == [1, 2, 3]
    assert examined == 3
    assert [c.get("cursor") for c in gql.calls] == [None, "c1", "c2"]


def test_fetch_stops_at_first_pr_older_than_the_window() -> None:
    gql = FakeGraphQL(
        {
            None: make_page(
                [make_pr(1, []), make_pr(2, [], updated_age=120), make_pr(3, [])], "never"
            )
        }
    )

    prs, examined = rep.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))

    assert [p["number"] for p in prs] == [1]
    assert examined == 1
    assert len(gql.calls) == 1


def test_fetch_pages_threads_of_a_pr_with_more_than_one_page() -> None:
    first = make_pr(7, [make_thread("A")])
    first["reviewThreads"]["pageInfo"] = {"hasNextPage": True, "endCursor": "t1"}
    gql = FakeGraphQL(
        {None: make_page([first])},
        {
            (7, "t1"): {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "pageInfo": {"hasNextPage": True, "endCursor": "t2"},
                            "nodes": [make_thread("B")],
                        }
                    }
                }
            },
            (7, "t2"): {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": [make_thread("C")],
                        }
                    }
                }
            },
        },
    )

    prs, _ = rep.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))

    assert [t["id"] for t in prs[0]["threads"]] == ["A", "B", "C"]


def test_fetch_fails_loud_when_a_pr_page_cursor_is_missing() -> None:
    page = make_page([make_pr(1, [])], "x")
    page["repository"]["pullRequests"]["pageInfo"]["endCursor"] = None
    gql = FakeGraphQL({None: page})

    with pytest.raises(rep.FetchError, match="missing pagination cursor"):
        rep.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))


def test_fetch_fails_loud_when_page_info_is_absent() -> None:
    page = make_page([make_pr(1, [])])
    del page["repository"]["pullRequests"]["pageInfo"]

    with pytest.raises(rep.FetchError, match="missing pagination info"):
        rep.fetch_pull_requests(FakeGraphQL({None: page}), "o", "r", NOW - timedelta(days=90))


def test_fetch_fails_loud_when_a_thread_cursor_is_missing() -> None:
    pr = make_pr(7, [make_thread("A")])
    pr["reviewThreads"]["pageInfo"] = {"hasNextPage": True, "endCursor": ""}

    with pytest.raises(rep.FetchError, match="PR #7 threads"):
        rep.fetch_pull_requests(
            FakeGraphQL({None: make_page([pr])}), "o", "r", NOW - timedelta(days=90)
        )


def test_fetch_fails_loud_at_the_pr_page_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rep, "MAX_PR_PAGES", 2)
    gql = FakeGraphQL(
        {
            None: make_page([make_pr(1, [])], "c1"),
            "c1": make_page([make_pr(2, [])], "c2"),
            "c2": make_page([]),
        }
    )

    with pytest.raises(rep.FetchError, match="exceeded 2 pages"):
        rep.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))


def test_fetch_fails_loud_at_the_thread_page_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rep, "MAX_THREAD_PAGES", 1)
    pr = make_pr(7, [])
    pr["reviewThreads"]["pageInfo"] = {"hasNextPage": True, "endCursor": "t1"}
    more = {
        "repository": {
            "pullRequest": {
                "reviewThreads": {
                    "pageInfo": {"hasNextPage": True, "endCursor": "t2"},
                    "nodes": [],
                }
            }
        }
    }
    gql = FakeGraphQL({None: make_page([pr])}, {(7, "t1"): more})

    with pytest.raises(rep.FetchError, match="later threads were not read"):
        rep.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))


def test_fetch_carries_the_pr_body_for_the_trailer_check() -> None:
    gql = FakeGraphQL({None: make_page([make_pr(9, [], body=TRAILER_BODY)])})

    prs, _ = rep.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))

    assert rep.AGENT_TRAILER in prs[0]["body"]


def test_build_report_counts_trailer_prs_authored_under_the_owner_login() -> None:
    prs = [
        make_pr(n, [make_thread(f"T{n}", author=HUMAN)], author=HUMAN, body=TRAILER_BODY)
        for n in (1, 2, 3)
    ]
    prs.append(make_pr(4, [make_thread("T4", author=HUMAN)], author=HUMAN))

    report = rep.build_report(FakeGraphQL({None: make_page(prs)}), "o", "r", {}, NOW)

    assert report["examined"]["pull_requests"] == 4
    assert report["examined"]["agent_pull_requests"] == 3
    assert report["examined"]["trailer_pull_requests"] == 3
    assert report["examined"]["interventions"] == 3
    assert report["cluster_count"] == 2


def test_build_report_finds_a_cluster_at_three_prs() -> None:
    report = rep.build_report(three_repeat_pages(), "o", "r", {}, NOW)

    assert report["as_of"] == "2026-11-10"
    assert report["repository"] == "o/r"
    assert report["cluster_count"] == 2
    assert {(c["signal"], c["key"]) for c in report["clusters"]} == {
        ("rule", "ADR-042"),
        ("area", "a"),
    }
    assert report["examined"]["pull_requests"] == 3
    assert report["examined"]["agent_pull_requests"] == 3
    assert report["examined"]["trailer_pull_requests"] == 0


def test_build_report_with_two_prs_reports_an_explicit_zero() -> None:
    prs = [make_pr(n, [make_thread(f"T{n}")]) for n in (1, 2)]

    report = rep.build_report(FakeGraphQL({None: make_page(prs)}), "o", "r", {}, NOW)

    assert report["cluster_count"] == 0
    assert report["clusters"] == []
    assert report["examined"]["interventions"] == 2
