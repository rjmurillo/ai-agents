"""Tests for scripts/report_reviewer_intervention_clusters.py."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from scripts import report_reviewer_intervention_clusters as rep

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
BOT = {"login": "rjmurillo-bot", "__typename": "Bot"}
HUMAN = {"login": "rjmurillo", "__typename": "User"}


def _ts(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def _thread(tid: str, *, author: dict | None = HUMAN, body: str = "ADR-042", path="a/b.py", age=1):
    return {
        "id": tid,
        "comments": {
            "nodes": [
                {
                    "id": f"c-{tid}",
                    "body": body,
                    "createdAt": _ts(age),
                    "path": path,
                    "author": author,
                }
            ]
        },
    }


def _pr(number: int, threads: list[dict], *, author: dict | None = BOT, updated_age: float = 1):
    return {
        "number": number,
        "updatedAt": _ts(updated_age),
        "author": author,
        "reviewThreads": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": threads,
        },
    }


def _page(prs: list[dict], next_cursor: str | None = None) -> dict:
    return {
        "repository": {
            "pullRequests": {
                "pageInfo": {"hasNextPage": next_cursor is not None, "endCursor": next_cursor},
                "nodes": prs,
            }
        }
    }


class FakeGraphQL:
    """Serve scripted pages. Keyed on the PR cursor or the thread-page request."""

    def __init__(self, pr_pages: dict[str | None, dict], thread_pages: dict | None = None):
        self.pr_pages = pr_pages
        self.thread_pages = thread_pages or {}
        self.calls: list[dict] = []

    def __call__(self, query: str, variables: dict[str, Any] | None = None) -> dict:
        variables = variables or {}
        self.calls.append(variables)
        if "number" in variables:
            return self.thread_pages[(variables["number"], variables["cursor"])]
        return self.pr_pages[variables.get("cursor")]


def _three_repeat_pages() -> FakeGraphQL:
    prs = [_pr(n, [_thread(f"T{n}")]) for n in (1, 2, 3)]
    return FakeGraphQL({None: _page(prs)})


def test_fetch_follows_every_pr_page_until_no_next_page() -> None:
    gql = FakeGraphQL(
        {
            None: _page([_pr(1, [])], "c1"),
            "c1": _page([_pr(2, [])], "c2"),
            "c2": _page([_pr(3, [])]),
        }
    )

    prs, examined = rep.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))

    assert [p["number"] for p in prs] == [1, 2, 3]
    assert examined == 3
    assert [c.get("cursor") for c in gql.calls] == [None, "c1", "c2"]


def test_fetch_stops_at_first_pr_older_than_the_window() -> None:
    gql = FakeGraphQL({None: _page([_pr(1, []), _pr(2, [], updated_age=120), _pr(3, [])], "never")})

    prs, examined = rep.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))

    assert [p["number"] for p in prs] == [1]
    assert examined == 1
    assert len(gql.calls) == 1


def test_fetch_pages_threads_of_a_pr_with_more_than_one_page() -> None:
    first = _pr(7, [_thread("A")])
    first["reviewThreads"]["pageInfo"] = {"hasNextPage": True, "endCursor": "t1"}
    gql = FakeGraphQL(
        {None: _page([first])},
        {
            (7, "t1"): {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "pageInfo": {"hasNextPage": True, "endCursor": "t2"},
                            "nodes": [_thread("B")],
                        }
                    }
                }
            },
            (7, "t2"): {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": [_thread("C")],
                        }
                    }
                }
            },
        },
    )

    prs, _ = rep.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))

    assert [t["id"] for t in prs[0]["threads"]] == ["A", "B", "C"]


def test_fetch_fails_loud_when_a_pr_page_cursor_is_missing() -> None:
    page = _page([_pr(1, [])], "x")
    page["repository"]["pullRequests"]["pageInfo"]["endCursor"] = None
    gql = FakeGraphQL({None: page})

    with pytest.raises(rep.FetchError, match="missing pagination cursor"):
        rep.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))


def test_fetch_fails_loud_when_page_info_is_absent() -> None:
    page = _page([_pr(1, [])])
    del page["repository"]["pullRequests"]["pageInfo"]

    with pytest.raises(rep.FetchError, match="missing pagination info"):
        rep.fetch_pull_requests(FakeGraphQL({None: page}), "o", "r", NOW - timedelta(days=90))


def test_fetch_fails_loud_when_a_thread_cursor_is_missing() -> None:
    pr = _pr(7, [_thread("A")])
    pr["reviewThreads"]["pageInfo"] = {"hasNextPage": True, "endCursor": ""}

    with pytest.raises(rep.FetchError, match="PR #7 threads"):
        rep.fetch_pull_requests(
            FakeGraphQL({None: _page([pr])}), "o", "r", NOW - timedelta(days=90)
        )


def test_fetch_fails_loud_at_the_pr_page_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rep, "MAX_PR_PAGES", 2)
    gql = FakeGraphQL(
        {None: _page([_pr(1, [])], "c1"), "c1": _page([_pr(2, [])], "c2"), "c2": _page([])}
    )

    with pytest.raises(rep.FetchError, match="exceeded 2 pages"):
        rep.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))


def test_fetch_fails_loud_at_the_thread_page_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rep, "MAX_THREAD_PAGES", 1)
    pr = _pr(7, [])
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
    gql = FakeGraphQL({None: _page([pr])}, {(7, "t1"): more})

    with pytest.raises(rep.FetchError, match="later threads were not read"):
        rep.fetch_pull_requests(gql, "o", "r", NOW - timedelta(days=90))


def test_extract_keeps_only_human_threads_on_agent_prs() -> None:
    prs = [
        {"number": 1, "author": BOT, "threads": [_thread("keep")]},
        {"number": 2, "author": HUMAN, "threads": [_thread("human-pr")]},
        {
            "number": 3,
            "author": {"login": "dependabot[bot]", "__typename": "Bot"},
            "threads": [_thread("dependabot")],
        },
        {"number": 4, "author": None, "threads": [_thread("ghost-author")]},
        {
            "number": 5,
            "author": BOT,
            "threads": [
                _thread(
                    "bot-reviewer",
                    author={"login": "copilot-pull-request-reviewer", "__typename": "Bot"},
                ),
                _thread("self", author=BOT),
                _thread("no-author", author=None),
            ],
        },
    ]

    interventions, agent_prs = rep.extract_interventions(prs)

    assert [i["thread_id"] for i in interventions] == ["keep"]
    assert agent_prs == 2


def test_extract_skips_a_thread_with_no_comments() -> None:
    thread = {"id": "empty", "comments": {"nodes": []}}

    interventions, agent_prs = rep.extract_interventions(
        [{"number": 1, "author": BOT, "threads": [thread]}]
    )

    assert interventions == []
    assert agent_prs == 1


def test_build_report_finds_a_cluster_at_three_prs() -> None:
    report = rep.build_report(_three_repeat_pages(), "o", "r", {}, NOW)

    assert report["as_of"] == "2026-11-10"
    assert report["repository"] == "o/r"
    assert report["cluster_count"] == 2
    assert {(c["signal"], c["key"]) for c in report["clusters"]} == {
        ("rule", "ADR-042"),
        ("area", "a"),
    }
    assert report["examined"]["pull_requests"] == 3
    assert report["examined"]["agent_pull_requests"] == 3


def test_build_report_with_two_prs_reports_an_explicit_zero() -> None:
    prs = [_pr(n, [_thread(f"T{n}")]) for n in (1, 2)]

    report = rep.build_report(FakeGraphQL({None: _page(prs)}), "o", "r", {}, NOW)

    assert report["cluster_count"] == 0
    assert report["clusters"] == []
    assert report["examined"]["interventions"] == 2


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(rep, "workspace", str(tmp_path))
    monkeypatch.setattr(
        rep, "resolve_repo_params", lambda owner, repo: type("R", (), {"owner": "o", "repo": "r"})()
    )
    return tmp_path


def test_main_writes_the_report_and_exits_zero(workspace: Path, caplog) -> None:
    caplog.set_level("INFO")

    code = rep.main(["--output", "out/report.json"], graphql=_three_repeat_pages())

    assert code == 0
    written = json.loads((workspace / "out" / "report.json").read_text(encoding="utf-8"))
    assert written["cluster_count"] == 2
    assert "2 clusters in 3 interventions" in caplog.text


def test_main_reads_dispositions_from_the_named_file(workspace: Path) -> None:
    entries = {f"{n}:0": {"disposition": "not-applicable", "reason": "r"} for n in range(3)}
    (workspace / "disp.json").write_text(json.dumps(entries), encoding="utf-8")
    gql = FakeGraphQL({None: _page([])})

    code = rep.main(["--output", "r.json", "--dispositions-file", "disp.json"], graphql=gql)

    written = json.loads((workspace / "r.json").read_text(encoding="utf-8"))
    assert code == 0
    assert [(c["signal"], c["key"], c["count"]) for c in written["clusters"]] == [
        ("disposition", "not-applicable", 3)
    ]


def test_main_treats_a_missing_dispositions_file_as_empty(workspace: Path) -> None:
    code = rep.main(["--output", "r.json"], graphql=FakeGraphQL({None: _page([])}))

    written = json.loads((workspace / "r.json").read_text(encoding="utf-8"))
    assert code == 0
    assert written["examined"]["dispositions"] == 0
    assert written["cluster_count"] == 0


@pytest.mark.parametrize("content", ["not json", "[1, 2]"])
def test_main_exits_2_on_a_bad_dispositions_file(workspace: Path, content: str) -> None:
    (workspace / "disp.json").write_text(content, encoding="utf-8")

    code = rep.main(
        ["--output", "r.json", "--dispositions-file", "disp.json"],
        graphql=FakeGraphQL({None: _page([])}),
    )

    assert code == 2
    assert not (workspace / "r.json").exists()


@pytest.mark.parametrize("output", ["../escape.json", "report.txt"])
def test_main_exits_2_on_an_output_path_outside_the_contract(workspace: Path, output: str) -> None:
    code = rep.main(["--output", output], graphql=FakeGraphQL({None: _page([])}))

    assert code == 2


def test_main_exits_2_on_bad_arguments(workspace: Path) -> None:
    assert rep.main(["--no-such-flag"]) == 2


def test_main_exits_3_and_writes_nothing_when_pagination_is_incomplete(workspace: Path) -> None:
    page = _page([_pr(1, [])], "x")
    page["repository"]["pullRequests"]["pageInfo"]["endCursor"] = None

    code = rep.main(["--output", "r.json"], graphql=FakeGraphQL({None: page}))

    assert code == 3
    assert not (workspace / "r.json").exists()


def test_main_exits_3_on_a_malformed_intervention(workspace: Path) -> None:
    bad = _pr(1, [_thread("T1")])
    bad["reviewThreads"]["nodes"][0]["comments"]["nodes"][0]["createdAt"] = "yesterday"

    code = rep.main(["--output", "r.json"], graphql=FakeGraphQL({None: _page([bad])}))

    assert code == 3
    assert not (workspace / "r.json").exists()


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("GraphQL request failed: HTTP 502", 3),
        ("GraphQL request failed: HTTP 401 bad credentials", 4),
    ],
)
def test_main_maps_api_failures_to_external_or_auth(
    workspace: Path, message: str, expected: int
) -> None:
    def boom(query: str, variables: dict | None = None) -> dict:
        raise RuntimeError(message)

    assert rep.main(["--output", "r.json"], graphql=boom) == expected
    assert not (workspace / "r.json").exists()
