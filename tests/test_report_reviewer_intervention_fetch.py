"""Tests for the pull request and thread fetch in report_reviewer_intervention_clusters.py."""

from __future__ import annotations

import subprocess
from datetime import timedelta
from typing import Any

import pytest

from scripts import report_reviewer_intervention_clusters as rep
from scripts import reviewer_intervention_fetch as fetch
from tests.report_reviewer_intervention_helpers import (
    BOT,
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

    prs, examined = fetch.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))

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

    prs, examined = fetch.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))

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

    prs, _ = fetch.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))

    assert [t["id"] for t in prs[0]["threads"]] == ["A", "B", "C"]


def test_fetch_fails_loud_when_a_pr_page_cursor_is_missing() -> None:
    page = make_page([make_pr(1, [])], "x")
    page["repository"]["pullRequests"]["pageInfo"]["endCursor"] = None
    gql = FakeGraphQL({None: page})

    with pytest.raises(fetch.FetchError, match="missing pagination cursor"):
        fetch.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))


def test_fetch_fails_loud_when_page_info_is_absent() -> None:
    page = make_page([make_pr(1, [])])
    del page["repository"]["pullRequests"]["pageInfo"]

    with pytest.raises(fetch.FetchError, match="missing pagination info"):
        fetch.fetch_pull_requests(FakeGraphQL({None: page}), "o", "r", NOW - timedelta(days=90))


def test_fetch_fails_loud_when_a_thread_cursor_is_missing() -> None:
    pr = make_pr(7, [make_thread("A")])
    pr["reviewThreads"]["pageInfo"] = {"hasNextPage": True, "endCursor": ""}

    with pytest.raises(fetch.FetchError, match="PR #7 threads"):
        fetch.fetch_pull_requests(
            FakeGraphQL({None: make_page([pr])}), "o", "r", NOW - timedelta(days=90)
        )


def test_fetch_fails_loud_at_the_pr_page_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch, "MAX_PR_PAGES", 2)
    gql = FakeGraphQL(
        {
            None: make_page([make_pr(1, [])], "c1"),
            "c1": make_page([make_pr(2, [])], "c2"),
            "c2": make_page([]),
        }
    )

    with pytest.raises(fetch.FetchError, match="exceeded 2 pages"):
        fetch.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))


def test_fetch_fails_loud_at_the_thread_page_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch, "MAX_THREAD_PAGES", 1)
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

    with pytest.raises(fetch.FetchError, match="later threads were not read"):
        fetch.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))


def test_fetch_carries_the_pr_body_for_the_trailer_check() -> None:
    gql = FakeGraphQL({None: make_page([make_pr(9, [], body=TRAILER_BODY)])})

    prs, _ = fetch.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))

    assert "Generated with [Claude Code]" in prs[0]["body"]


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


def test_fetch_skips_and_counts_a_pull_request_that_repeats_across_pages() -> None:
    gql = FakeGraphQL(
        {
            None: make_page([make_pr(1, []), make_pr(2, [])], "c1"),
            "c1": make_page([make_pr(2, []), make_pr(3, [])]),
        }
    )
    stats: dict[str, int] = {}

    prs, examined = fetch.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90), stats)

    assert [p["number"] for p in prs] == [1, 2, 3]
    assert examined == 3
    assert stats["duplicate_pull_requests_skipped"] == 1
    assert stats["pages"] == 2


def test_fetch_sums_the_graphql_cost_across_pages() -> None:
    first = make_page([make_pr(1, [])], "c1")
    first["rateLimit"] = {"cost": 26, "remaining": 4900}
    second = make_page([make_pr(2, [])])
    second["rateLimit"] = {"cost": 25, "remaining": 4875}
    stats: dict[str, int] = {}

    fetch.fetch_pull_requests(
        FakeGraphQL({None: first, "c1": second}), "o", "r", NOW - timedelta(days=90), stats
    )

    assert stats["graphql_cost"] == 51


def test_fetch_tolerates_a_response_with_no_rate_limit_block() -> None:
    stats: dict[str, int] = {}

    fetch.fetch_pull_requests(
        FakeGraphQL({None: make_page([make_pr(1, [])])}), "o", "r", NOW - timedelta(days=90), stats
    )

    assert stats["graphql_cost"] == 0


def test_fetch_logs_progress_every_n_pages(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(fetch, "PROGRESS_EVERY_PAGES", 1)
    caplog.set_level("INFO")
    gql = FakeGraphQL({None: make_page([make_pr(1, [])], "c1"), "c1": make_page([])})

    fetch.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))

    assert "read 1 pages" in caplog.text
    assert "read 2 pages" in caplog.text


def test_fetch_fails_loud_on_a_null_node_instead_of_dropping_it() -> None:
    page = make_page([make_pr(1, [])])
    page["repository"]["pullRequests"]["nodes"].append(None)

    with pytest.raises(fetch.FetchError, match="null node"):
        fetch.fetch_pull_requests(FakeGraphQL({None: page}), "o", "r", NOW - timedelta(days=90))


def test_fetch_fails_loud_on_a_null_thread_node() -> None:
    pr = make_pr(1, [make_thread("A")])
    pr["reviewThreads"]["nodes"].append(None)

    with pytest.raises(fetch.FetchError, match="PR #1 threads"):
        fetch.fetch_pull_requests(
            FakeGraphQL({None: make_page([pr])}), "o", "r", NOW - timedelta(days=90)
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda page: page.__setitem__("repository", None), "repository is not an object"),
        (
            lambda page: page["repository"]["pullRequests"].pop("nodes"),
            "missing nodes for pull requests",
        ),
        (
            lambda page: page["repository"]["pullRequests"]["nodes"][0].__setitem__("number", "x"),
            "numeric `number`",
        ),
        (
            lambda page: page["repository"]["pullRequests"]["nodes"][0].__setitem__(
                "reviewThreads", None
            ),
            "reviewThreads is not an object",
        ),
    ],
)
def test_fetch_fails_loud_on_a_malformed_response_shape(mutate, message: str) -> None:
    page = make_page([make_pr(1, [])])
    mutate(page)

    with pytest.raises(fetch.FetchError, match=message):
        fetch.fetch_pull_requests(FakeGraphQL({None: page}), "o", "r", NOW - timedelta(days=90))


def test_fetch_fails_loud_when_the_response_is_not_an_object() -> None:
    def not_an_object(query: str, variables: dict[str, Any] | None = None) -> Any:
        return []

    with pytest.raises(fetch.FetchError, match="not an object"):
        fetch.fetch_pull_requests(not_an_object, "o", "r", NOW - timedelta(days=90))


def test_the_pr_query_asks_for_the_documented_thread_page_size() -> None:
    assert f"reviewThreads(first: {fetch.PR_PAGE_THREADS})" in fetch._PRS_QUERY
    assert fetch.PR_PAGE_THREADS < 50


def test_fetch_counts_the_cost_of_thread_follow_up_queries() -> None:
    pr = make_pr(7, [make_thread("A")])
    pr["reviewThreads"]["pageInfo"] = {"hasNextPage": True, "endCursor": "t1"}
    first = make_page([pr])
    first["rateLimit"] = {"cost": 11, "remaining": 4000}
    follow_up = {
        "rateLimit": {"cost": 1, "remaining": 3999},
        "repository": {
            "pullRequest": {
                "reviewThreads": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [make_thread("B")],
                }
            }
        },
    }
    stats: dict[str, int] = {}

    fetch.fetch_pull_requests(
        FakeGraphQL({None: first}, {(7, "t1"): follow_up}),
        "o",
        "r",
        NOW - timedelta(days=90),
        stats,
    )

    assert stats["graphql_cost"] == 12


def test_fetch_returns_normalized_pr_and_thread_records() -> None:
    thread = make_thread("T1", body="ADR-042", path="a/b.py", association="MEMBER")
    page = make_page([make_pr(5, [thread], author=BOT, body=TRAILER_BODY, association="OWNER")])

    prs, _ = fetch.fetch_pull_requests(
        FakeGraphQL({None: page}), "o", "r", NOW - timedelta(days=90)
    )

    assert prs[0]["author_login"] == BOT["login"]
    assert prs[0]["author_kind"] == "Bot"
    assert prs[0]["author_association"] == "OWNER"
    assert prs[0]["threads"] == [
        {
            "id": "T1",
            "opener": {
                "login": HUMAN["login"],
                "kind": "User",
                "association": "MEMBER",
                "created_at": thread["comments"]["nodes"][0]["createdAt"],
                "body": "ADR-042",
                "path": "a/b.py",
            },
        }
    ]


def test_fetch_normalizes_a_missing_author_to_an_empty_login() -> None:
    page = make_page([make_pr(5, [make_thread("T1", author=None)], author=None)])

    prs, _ = fetch.fetch_pull_requests(
        FakeGraphQL({None: page}), "o", "r", NOW - timedelta(days=90)
    )

    assert prs[0]["author_login"] == ""
    assert prs[0]["author_kind"] is None
    assert prs[0]["threads"][0]["opener"]["login"] == ""


def test_fetch_normalizes_a_thread_without_comments_to_no_opener() -> None:
    empty = {"id": "E1", "comments": {"nodes": []}}
    page = make_page([make_pr(5, [empty])])

    prs, _ = fetch.fetch_pull_requests(
        FakeGraphQL({None: page}), "o", "r", NOW - timedelta(days=90)
    )

    assert prs[0]["threads"] == [{"id": "E1", "opener": None}]


def test_fetch_raises_on_a_thread_without_an_id() -> None:
    thread = make_thread("x")
    del thread["id"]

    with pytest.raises(fetch.FetchError, match="has no id"):
        fetch.fetch_pull_requests(
            FakeGraphQL({None: make_page([make_pr(5, [thread])])}),
            "o",
            "r",
            NOW - timedelta(days=90),
        )


def test_fetch_raises_on_a_malformed_thread_comments_object() -> None:
    bad = {"id": "t", "comments": None}

    with pytest.raises(fetch.FetchError, match="not an object"):
        fetch.fetch_pull_requests(
            FakeGraphQL({None: make_page([make_pr(5, [bad])])}),
            "o",
            "r",
            NOW - timedelta(days=90),
        )


class _FlakyOnce:
    """Raise TimeoutExpired on the first call, then serve the page."""

    def __init__(self, page: dict[str, Any]) -> None:
        self.page = page
        self.calls = 0

    def __call__(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls += 1
        if self.calls == 1:
            raise subprocess.TimeoutExpired(cmd="gh", timeout=30)
        return self.page


def test_fetch_retries_a_page_once_after_a_gh_timeout(caplog: pytest.LogCaptureFixture) -> None:
    flaky = _FlakyOnce(make_page([make_pr(1, [])]))

    prs, _ = fetch.fetch_pull_requests(flaky, "o", "r", NOW - timedelta(days=90))

    assert [p["number"] for p in prs] == [1]
    assert flaky.calls == 2
    assert "timed out; retrying once" in caplog.text


def test_fetch_gives_up_when_the_retry_also_times_out() -> None:
    def always(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        raise subprocess.TimeoutExpired(cmd="gh", timeout=30)

    with pytest.raises(subprocess.TimeoutExpired):
        fetch.fetch_pull_requests(always, "o", "r", NOW - timedelta(days=90))


def test_fetch_warns_when_a_response_has_no_rate_limit_block(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fetch.fetch_pull_requests(
        FakeGraphQL({None: make_page([make_pr(1, [])])}), "o", "r", NOW - timedelta(days=90)
    )

    assert "no rateLimit block" in caplog.text
