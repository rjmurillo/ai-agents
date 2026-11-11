"""Tests for the agent PR and human intervention filter of the cluster report."""

from __future__ import annotations

from typing import Any

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
)

OUTSIDER = {"login": "outsider", "__typename": "User"}
COPILOT = {"login": "copilot-pull-request-reviewer", "__typename": "Bot"}


def opener(
    login: str = "rjmurillo",
    kind: str | None = "User",
    association: str | None = "OWNER",
) -> dict[str, Any]:
    return {
        "login": login,
        "kind": kind,
        "association": association,
        "created_at": "2026-11-09T00:00:00Z",
        "body": "ADR-042",
        "path": "a/b.py",
    }


def thread(tid: str, who: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": tid, "opener": opener() if who is None else who}


def pr(
    number: int,
    threads: list[dict[str, Any]],
    *,
    login: str = "rjmurillo-bot",
    kind: str | None = "Bot",
    association: str | None = "OWNER",
    body: str = "",
) -> dict[str, Any]:
    return {
        "number": number,
        "author_login": login,
        "author_kind": kind,
        "author_association": association,
        "body": body,
        "threads": threads,
    }


def test_extract_keeps_human_threads_on_bot_authored_prs() -> None:
    interventions, counts = rep.extract_interventions([pr(1, [thread("keep")])])

    assert [i["thread_id"] for i in interventions] == ["keep"]
    assert counts["agent_pull_requests"] == 1
    assert counts["trailer_pull_requests"] == 0


def test_extract_carries_the_opener_fields_into_the_intervention() -> None:
    interventions, _ = rep.extract_interventions([pr(1, [thread("t")])])

    assert interventions == [
        {
            "pr": 1,
            "thread_id": "t",
            "created_at": "2026-11-09T00:00:00Z",
            "body": "ADR-042",
            "path": "a/b.py",
        }
    ]


def test_extract_keeps_owner_threads_on_a_trailer_pr_opened_under_the_owner_login() -> None:
    prs = [pr(2, [thread("owner")], login="rjmurillo", kind="User", body=TRAILER_BODY)]

    interventions, counts = rep.extract_interventions(prs)

    assert [i["thread_id"] for i in interventions] == ["owner"]
    assert counts["agent_pull_requests"] == 1
    assert counts["trailer_pull_requests"] == 1
    assert counts["interventions_by_pr_author"] == 1


def test_extract_excludes_a_human_pr_without_the_trailer() -> None:
    prs = [pr(3, [thread("t")], login="rjmurillo", kind="User")]

    interventions, counts = rep.extract_interventions(prs)

    assert interventions == []
    assert counts["agent_pull_requests"] == 0
    assert counts["threads_seen"] == 0


@pytest.mark.parametrize("login", ["dependabot", "dependabot[bot]", "renovate", "renovate[bot]"])
def test_extract_excludes_dependency_bots(login: str) -> None:
    interventions, counts = rep.extract_interventions([pr(4, [thread("t")], login=login)])

    assert interventions == []
    assert counts["agent_pull_requests"] == 0


def test_extract_excludes_a_dependency_bot_pr_even_with_the_trailer() -> None:
    _, counts = rep.extract_interventions(
        [pr(5, [thread("t")], login="renovate", body=TRAILER_BODY)]
    )

    assert counts["agent_pull_requests"] == 0


@pytest.mark.parametrize("association", ["NONE", "CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", None])
def test_extract_ignores_a_trailer_on_a_pr_from_an_author_without_standing(
    association: str | None,
) -> None:
    prs = [
        pr(
            6,
            [thread("t")],
            login="outsider",
            kind="User",
            association=association,
            body=TRAILER_BODY,
        )
    ]

    interventions, counts = rep.extract_interventions(prs)

    assert interventions == []
    assert counts["agent_pull_requests"] == 0
    assert counts["trailer_pull_requests"] == 0


@pytest.mark.parametrize("association", ["OWNER", "MEMBER", "COLLABORATOR"])
def test_extract_honours_a_trailer_from_an_author_with_standing(association: str) -> None:
    prs = [
        pr(
            7,
            [thread("t")],
            login="rjmurillo",
            kind="User",
            association=association,
            body=TRAILER_BODY,
        )
    ]

    interventions, counts = rep.extract_interventions(prs)

    assert [i["thread_id"] for i in interventions] == ["t"]
    assert counts["trailer_pull_requests"] == 1


def test_extract_honours_a_bot_actor_regardless_of_association() -> None:
    prs = [pr(8, [thread("t")], login="copilot-swe-agent", kind="Bot", association="NONE")]

    interventions, counts = rep.extract_interventions(prs)

    assert [i["thread_id"] for i in interventions] == ["t"]
    assert counts["agent_pull_requests"] == 1


def test_extract_does_not_treat_a_user_account_named_like_a_bot_as_an_agent() -> None:
    prs = [pr(9, [thread("t")], login="evil-bot", kind="User", association="NONE")]

    interventions, counts = rep.extract_interventions(prs)

    assert interventions == []
    assert counts["agent_pull_requests"] == 0


def test_extract_counts_each_filter_so_a_drop_is_visible() -> None:
    threads = [
        thread("kept"),
        thread("bot", opener("copilot-pull-request-reviewer", "Bot", "NONE")),
        thread("no-author", opener("", None, None)),
        thread("outsider", opener("outsider", "User", "NONE")),
        {"id": "empty", "opener": None},
    ]

    interventions, counts = rep.extract_interventions([pr(10, threads)])

    assert [i["thread_id"] for i in interventions] == ["kept"]
    assert counts["threads_seen"] == 5
    assert counts["threads_excluded_bot_or_unknown"] == 2
    assert counts["threads_excluded_no_standing"] == 1
    assert counts["threads_without_comments"] == 1
    assert counts["interventions_by_pr_author"] == 0
    dropped = sum(
        counts[k]
        for k in (
            "threads_excluded_bot_or_unknown",
            "threads_excluded_no_standing",
            "threads_without_comments",
        )
    )
    assert len(interventions) + dropped == counts["threads_seen"]


def test_extract_treats_a_pr_with_no_author_as_agent_only_when_the_trailer_is_present() -> None:
    plain, plain_counts = rep.extract_interventions(
        [pr(11, [thread("a")], login="", kind=None, association="OWNER")]
    )
    marked, marked_counts = rep.extract_interventions(
        [pr(12, [thread("b")], login="", kind=None, association="OWNER", body=TRAILER_BODY)]
    )

    assert plain == []
    assert plain_counts["agent_pull_requests"] == 0
    assert [i["thread_id"] for i in marked] == ["b"]
    assert marked_counts["trailer_pull_requests"] == 1


def test_extract_raises_on_an_unknown_opener_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "review_clusters.classify_thread_opener", lambda login, is_bot, assoc: "new-verdict"
    )

    with pytest.raises(ValueError, match="unknown opener verdict"):
        rep.extract_interventions([pr(13, [thread("t")])])


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


def test_a_user_account_named_like_a_bot_cannot_mint_a_cluster() -> None:
    evil = {"login": "evil-bot", "__typename": "User"}
    prs = [
        make_pr(
            n,
            [make_thread(f"T{n}", author=HUMAN, association="OWNER")],
            author=evil,
            association="NONE",
        )
        for n in (1, 2, 3)
    ]

    report = rep.build_report(FakeGraphQL({None: make_page(prs)}), "o", "r", {}, NOW)

    assert report["examined"]["agent_pull_requests"] == 0
    assert report["cluster_count"] == 0
