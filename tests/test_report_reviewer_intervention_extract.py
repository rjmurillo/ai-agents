"""Tests for the agent PR and human intervention filter of the cluster report."""

from __future__ import annotations

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
)

OUTSIDER = {"login": "outsider", "__typename": "User"}


def _ex(
    number: int,
    author: dict | None,
    threads: list[dict],
    body: str = "",
    association: str | None = "OWNER",
) -> dict:
    return {
        "number": number,
        "author": author,
        "author_association": association,
        "body": body,
        "threads": threads,
    }


def test_extract_keeps_human_threads_on_bot_authored_prs() -> None:
    interventions, counts = rep.extract_interventions([_ex(1, BOT, [make_thread("keep")])])

    assert [i["thread_id"] for i in interventions] == ["keep"]
    assert counts["agent_pull_requests"] == 1
    assert counts["trailer_pull_requests"] == 0


def test_extract_keeps_owner_threads_on_a_trailer_pr_opened_under_the_owner_login() -> None:
    prs = [_ex(2, HUMAN, [make_thread("owner-correction", author=HUMAN)], body=TRAILER_BODY)]

    interventions, counts = rep.extract_interventions(prs)

    assert [i["thread_id"] for i in interventions] == ["owner-correction"]
    assert counts["agent_pull_requests"] == 1
    assert counts["trailer_pull_requests"] == 1
    assert counts["interventions_by_pr_author"] == 1


def test_extract_excludes_a_human_pr_without_the_trailer() -> None:
    prs = [_ex(3, HUMAN, [make_thread("t", author={"login": "other", "__typename": "User"})])]

    interventions, counts = rep.extract_interventions(prs)

    assert interventions == []
    assert counts["agent_pull_requests"] == 0
    assert counts["threads_seen"] == 0


@pytest.mark.parametrize("login", ["dependabot", "dependabot[bot]", "renovate", "renovate[bot]"])
def test_extract_excludes_dependency_bots(login: str) -> None:
    author = {"login": login, "__typename": "Bot"}

    interventions, counts = rep.extract_interventions([_ex(4, author, [make_thread("t")])])

    assert interventions == []
    assert counts["agent_pull_requests"] == 0


def test_extract_excludes_a_dependency_bot_pr_even_with_the_trailer() -> None:
    author = {"login": "renovate", "__typename": "Bot"}

    _, counts = rep.extract_interventions([_ex(5, author, [make_thread("t")], body=TRAILER_BODY)])

    assert counts["agent_pull_requests"] == 0


@pytest.mark.parametrize("association", ["NONE", "CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", None])
def test_extract_ignores_a_trailer_on_a_pr_from_an_author_without_standing(
    association: str | None,
) -> None:
    prs = [_ex(6, OUTSIDER, [make_thread("t")], body=TRAILER_BODY, association=association)]

    interventions, counts = rep.extract_interventions(prs)

    assert interventions == []
    assert counts["agent_pull_requests"] == 0
    assert counts["trailer_pull_requests"] == 0


@pytest.mark.parametrize("association", ["OWNER", "MEMBER", "COLLABORATOR"])
def test_extract_honours_a_trailer_from_an_author_with_standing(association: str) -> None:
    prs = [_ex(7, HUMAN, [make_thread("t")], body=TRAILER_BODY, association=association)]

    interventions, counts = rep.extract_interventions(prs)

    assert [i["thread_id"] for i in interventions] == ["t"]
    assert counts["trailer_pull_requests"] == 1


def test_extract_honours_a_bot_author_regardless_of_association() -> None:
    prs = [_ex(8, BOT, [make_thread("t")], association="NONE")]

    interventions, counts = rep.extract_interventions(prs)

    assert [i["thread_id"] for i in interventions] == ["t"]
    assert counts["agent_pull_requests"] == 1


def test_extract_counts_each_filter_so_a_drop_is_visible() -> None:
    copilot = {"login": "copilot-pull-request-reviewer", "__typename": "Bot"}
    threads = [
        make_thread("kept"),
        make_thread("bot", author=copilot),
        make_thread("no-author", author=None),
        make_thread("outsider", author=OUTSIDER, association="NONE"),
        {"id": "empty", "comments": {"nodes": []}},
    ]

    interventions, counts = rep.extract_interventions([_ex(9, BOT, threads)])

    assert [i["thread_id"] for i in interventions] == ["kept"]
    assert counts["threads_seen"] == 5
    assert counts["threads_excluded_bot_or_unknown"] == 2
    assert counts["threads_excluded_no_standing"] == 1
    assert counts["threads_without_comments"] == 1
    assert counts["interventions_by_pr_author"] == 0
    kept_and_dropped = len(interventions) + sum(
        counts[k]
        for k in (
            "threads_excluded_bot_or_unknown",
            "threads_excluded_no_standing",
            "threads_without_comments",
        )
    )
    assert kept_and_dropped == counts["threads_seen"]


def test_extract_treats_a_pr_with_no_author_as_agent_only_when_the_trailer_is_present() -> None:
    plain, plain_counts = rep.extract_interventions([_ex(10, None, [make_thread("a")])])
    marked, marked_counts = rep.extract_interventions(
        [_ex(11, None, [make_thread("b")], body=TRAILER_BODY)]
    )

    assert plain == []
    assert plain_counts["agent_pull_requests"] == 0
    assert [i["thread_id"] for i in marked] == ["b"]
    assert marked_counts["trailer_pull_requests"] == 1


def test_extract_raises_on_a_thread_without_an_id() -> None:
    thread = make_thread("x")
    del thread["id"]

    with pytest.raises(fetch.FetchError, match="has no id"):
        rep.extract_interventions([_ex(12, BOT, [thread])])


def test_extract_raises_on_a_malformed_thread_comments_object() -> None:
    with pytest.raises(fetch.FetchError, match="not an object"):
        rep.extract_interventions([_ex(13, BOT, [{"id": "t", "comments": None}])])


def test_outside_contributor_cannot_mint_a_cluster_with_a_forged_trailer() -> None:
    prs = [
        make_pr(
            n,
            [make_thread(f"T{n}", author=OUTSIDER, association="NONE")],
            author=OUTSIDER,
            body=TRAILER_BODY,
            association="NONE",
        )
        for n in (1, 2, 3)
    ]

    report = rep.build_report(FakeGraphQL({None: make_page(prs)}), "o", "r", {}, NOW)

    assert report["examined"]["agent_pull_requests"] == 0
    assert report["examined"]["interventions"] == 0
    assert report["cluster_count"] == 0


def test_maintainer_threads_on_an_outsiders_forged_trailer_prs_do_not_count() -> None:
    prs = [
        make_pr(
            n,
            [make_thread(f"T{n}", author=HUMAN, association="OWNER")],
            author=OUTSIDER,
            body=TRAILER_BODY,
            association="NONE",
        )
        for n in (1, 2, 3)
    ]

    report = rep.build_report(FakeGraphQL({None: make_page(prs)}), "o", "r", {}, NOW)

    assert report["examined"]["interventions"] == 0
    assert report["cluster_count"] == 0
