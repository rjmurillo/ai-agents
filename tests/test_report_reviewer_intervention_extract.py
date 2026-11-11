"""Tests for the agent PR and human intervention filter of the cluster report."""

from __future__ import annotations

import pytest

from scripts import report_reviewer_intervention_clusters as rep
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


def _ex(number: int, author: dict | None, threads: list[dict], body: str = "") -> dict:
    return {"number": number, "author": author, "body": body, "threads": threads}


def test_extract_keeps_human_threads_on_bot_authored_prs() -> None:
    interventions, counts = rep.extract_interventions([_ex(1, BOT, [make_thread("keep")])])

    assert [i["thread_id"] for i in interventions] == ["keep"]
    assert counts == {"agent_pull_requests": 1, "trailer_pull_requests": 0}


def test_extract_keeps_owner_threads_on_a_trailer_pr_opened_under_the_owner_login() -> None:
    prs = [_ex(2, HUMAN, [make_thread("owner-correction", author=HUMAN)], body=TRAILER_BODY)]

    interventions, counts = rep.extract_interventions(prs)

    assert [i["thread_id"] for i in interventions] == ["owner-correction"]
    assert counts == {"agent_pull_requests": 1, "trailer_pull_requests": 1}


def test_extract_excludes_a_human_pr_without_the_trailer() -> None:
    prs = [_ex(3, HUMAN, [make_thread("t", author={"login": "other", "__typename": "User"})])]

    interventions, counts = rep.extract_interventions(prs)

    assert interventions == []
    assert counts == {"agent_pull_requests": 0, "trailer_pull_requests": 0}


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


def test_extract_drops_bot_commenters_and_commenters_with_no_author() -> None:
    threads = [
        make_thread(
            "bot-reviewer",
            author={"login": "copilot-pull-request-reviewer", "__typename": "Bot"},
        ),
        make_thread("agent-bot", author=BOT),
        make_thread("no-author", author=None),
    ]

    interventions, counts = rep.extract_interventions([_ex(6, BOT, threads)])

    assert interventions == []
    assert counts["agent_pull_requests"] == 1


def test_extract_treats_a_pr_with_no_author_as_agent_only_when_the_trailer_is_present() -> None:
    plain, plain_counts = rep.extract_interventions([_ex(7, None, [make_thread("a")])])
    marked, marked_counts = rep.extract_interventions(
        [_ex(8, None, [make_thread("b")], body=TRAILER_BODY)]
    )

    assert plain == []
    assert plain_counts["agent_pull_requests"] == 0
    assert [i["thread_id"] for i in marked] == ["b"]
    assert marked_counts["trailer_pull_requests"] == 1


def test_extract_skips_a_thread_with_no_comments() -> None:
    thread = {"id": "empty", "comments": {"nodes": []}}

    interventions, counts = rep.extract_interventions([_ex(1, BOT, [thread])])

    assert interventions == []
    assert counts["agent_pull_requests"] == 1


@pytest.mark.parametrize(
    "association", ["NONE", "CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "MANNEQUIN"]
)
def test_extract_drops_threads_from_commenters_without_write_standing(association: str) -> None:
    prs = [_ex(1, HUMAN, [make_thread("t", association=association)], body=TRAILER_BODY)]

    interventions, counts = rep.extract_interventions(prs)

    assert interventions == []
    assert counts["trailer_pull_requests"] == 1


@pytest.mark.parametrize("association", ["OWNER", "MEMBER", "COLLABORATOR"])
def test_extract_keeps_threads_from_commenters_with_write_standing(association: str) -> None:
    prs = [_ex(1, HUMAN, [make_thread("t", association=association)], body=TRAILER_BODY)]

    interventions, _ = rep.extract_interventions(prs)

    assert [i["thread_id"] for i in interventions] == ["t"]


def test_outside_contributor_cannot_mint_a_cluster_with_a_forged_trailer() -> None:
    outsider = {"login": "outsider", "__typename": "User"}
    prs = [
        make_pr(
            n,
            [make_thread(f"T{n}", author=outsider, association="NONE")],
            author=outsider,
            body=TRAILER_BODY,
        )
        for n in (1, 2, 3)
    ]

    report = rep.build_report(FakeGraphQL({None: make_page(prs)}), "o", "r", {}, NOW)

    assert report["examined"]["trailer_pull_requests"] == 3
    assert report["examined"]["interventions"] == 0
    assert report["cluster_count"] == 0
