"""Tests for scripts/eval/_third_party_review_fetch.py and _third_party_review_findings.py.

The GraphQL seam is a callable keyed on the query text, so no network is used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._third_party_gap_test_support import eval_path, load_script

with eval_path():
    import _third_party_review_fetch as fetch
    import _third_party_review_findings as findings


def conn(nodes: list[Any], cursor: str | None = None) -> dict[str, Any]:
    return {"pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor}, "nodes": nodes}


def comment(login: str, body: str = "b") -> dict[str, Any]:
    return {
        "author": {"login": login},
        "body": body,
        "createdAt": "2026-11-01T00:00:00Z",
        "originalCommit": {"oid": "c" * 40},
    }


def thread(tid: str, *logins: str, more: str | None = None) -> dict[str, Any]:
    return {
        "id": tid,
        "path": "a.py",
        "originalLine": 3,
        "isResolved": True,
        "comments": conn([comment(x) for x in logins], more),
    }


def pr(number: int, threads: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "number": number,
        "title": f"pr {number}",
        "author": {"login": "rjmurillo"},
        "reviewThreads": threads or conn([]),
        "reviews": conn([]),
        "comments": conn([]),
    }


class Fake:
    """Answers each query from a script; records the variables of every call."""

    def __init__(self, pages: list[dict[str, Any]], remaining: int = 5000) -> None:
        self.pages = pages
        self.remaining = remaining
        self.calls: list[dict[str, Any]] = []

    def __call__(self, query: str, variables: dict[str, Any] | None) -> dict[str, Any]:
        self.calls.append(dict(variables or {}))
        page = self.pages.pop(0)
        return {"rateLimit": {"cost": 1, "remaining": self.remaining}, **page}


def prs_page(nodes: list[Any], cursor: str | None = None) -> dict[str, Any]:
    return {"repository": {"pullRequests": conn(nodes, cursor)}}


class TestFetch:
    def test_stops_at_the_limit(self) -> None:
        fake = Fake([prs_page([pr(3), pr(2)], "c1"), prs_page([pr(1)])])

        got = fetch.fetch_recent_pull_requests(fake, "o", "r", 2)

        assert [p["number"] for p in got] == [3, 2]
        assert len(fake.calls) == 1

    def test_follows_the_pr_cursor_until_no_next_page(self) -> None:
        fake = Fake([prs_page([pr(3)], "c1"), prs_page([pr(2)])])

        got = fetch.fetch_recent_pull_requests(fake, "o", "r", 10)

        assert [p["number"] for p in got] == [3, 2]
        assert fake.calls[1]["cursor"] == "c1"

    def test_nested_thread_page_is_drained_and_merged(self) -> None:
        first = pr(5, conn([thread("t1", "devin-ai-integration")], "tc"))
        more = {"repository": {"pullRequest": {"reviewThreads": conn([thread("t2", "cursor")])}}}
        fake = Fake([prs_page([first]), more])

        (got,) = fetch.fetch_recent_pull_requests(fake, "o", "r", 1)

        assert [t["id"] for t in got["reviewThreads"]] == ["t1", "t2"]

    def test_thread_comment_page_is_drained(self) -> None:
        first = pr(5, conn([thread("t1", "cursor", more="cc")]))
        more = {"node": {"comments": conn([comment("rjmurillo", "Fixed in abc1234")])}}
        fake = Fake([prs_page([first]), more])

        (got,) = fetch.fetch_recent_pull_requests(fake, "o", "r", 1)

        assert len(got["reviewThreads"][0]["comments"]) == 2

    def test_missing_cursor_raises(self) -> None:
        page = {"repository": {"pullRequests": {"pageInfo": {"hasNextPage": True}, "nodes": []}}}

        with pytest.raises(fetch.FetchError, match="cursor"):
            fetch.fetch_recent_pull_requests(Fake([page]), "o", "r", 5)

    def test_null_node_raises(self) -> None:
        with pytest.raises(fetch.FetchError, match="null node"):
            fetch.fetch_recent_pull_requests(Fake([prs_page([None])]), "o", "r", 5)

    def test_non_integer_number_raises(self) -> None:
        bad = pr(1)
        bad["number"] = "1"

        with pytest.raises(fetch.FetchError, match="numeric"):
            fetch.fetch_recent_pull_requests(Fake([prs_page([bad])]), "o", "r", 5)

    def test_low_budget_stops_before_the_next_request(self) -> None:
        fake = Fake([prs_page([pr(3)], "c1"), prs_page([pr(2)])], remaining=10)

        with pytest.raises(fetch.FetchError, match="budget low"):
            fetch.fetch_recent_pull_requests(fake, "o", "r", 10)
        assert len(fake.calls) == 1

    def test_non_positive_limit_is_refused(self) -> None:
        with pytest.raises(ValueError):
            fetch.fetch_recent_pull_requests(Fake([]), "o", "r", 0)


class TestFindings:
    @pytest.mark.parametrize(
        ("login", "name"),
        [
            ("coderabbitai[bot]", "coderabbit"),
            ("Cursor", "cursor"),
            ("devin-ai-integration", "devin"),
            ("copilot-pull-request-reviewer", "copilot"),
            ("rjmurillo", None),
            (None, None),
        ],
    )
    def test_bot_name(self, login: str | None, name: str | None) -> None:
        assert findings.bot_name(login) == name

    def test_keeps_only_bot_opened_threads_with_replies(self) -> None:
        prs = [
            {
                **pr(9),
                "reviewThreads": [
                    thread("t1", "cursor", "rjmurillo")
                    | {"comments": [comment("cursor"), comment("rjmurillo", "Fixed")]},
                    thread("t2", "rjmurillo") | {"comments": [comment("rjmurillo")]},
                    {"id": "t3", "comments": []},
                ],
            }
        ]

        (row,) = findings.extract_bot_threads(prs)

        assert (row["thread_id"], row["bot"], row["line"]) == ("t1", "cursor", 3)
        assert row["replies"][0]["body"] == "Fixed"
        assert row["commit"] == "c" * 40


def _load_miner() -> Any:
    return load_script("mine_third_party_review_findings")


class TestMinerCli:
    def test_summarize_counts_threads_per_bot(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        miner = _load_miner()
        dump = tmp_path / "dump.json"
        threads = [{"comments": [comment("cursor")], "id": "t", "isResolved": True}]
        dump.write_text(
            json.dumps({"pull_requests": [pr(4) | {"reviewThreads": threads}]}), encoding="utf-8"
        )

        code = miner.main(["--summarize", str(dump)])

        out = json.loads(capsys.readouterr().out)
        assert code == 0
        assert out["by_bot"] == {"cursor": {"threads": 1, "resolved": 1}}

    def test_fetch_without_output_exits_2(self) -> None:
        assert _load_miner().main(["--limit", "5"]) == 2

    def test_unreadable_dump_exits_2(self, tmp_path: Path) -> None:
        assert _load_miner().main(["--summarize", str(tmp_path / "none.json")]) == 2

    def test_dump_that_is_not_utf8_exits_2(self, tmp_path: Path) -> None:
        dump = tmp_path / "dump.json"
        dump.write_bytes(b'{"pull_requests": ["\xff"]}')

        assert _load_miner().main(["--summarize", str(dump)]) == 2

    @pytest.mark.parametrize(
        "text",
        [
            '{"other": 1}',
            "[1, 2]",
            '{"pull_requests": [1]}',
            '{"pull_requests": {}}',
            '{"pull_requests": ""}',
            '{"pull_requests": null}',
        ],
    )
    def test_dump_without_a_pull_request_list_exits_2(self, tmp_path: Path, text: str) -> None:
        dump = tmp_path / "dump.json"
        dump.write_text(text, encoding="utf-8")

        assert _load_miner().main(["--summarize", str(dump)]) == 2

    def test_non_positive_limit_exits_2(self) -> None:
        assert _load_miner().main(["--limit", "0", "--output", "x.json"]) == 2


class TestPageCaps:
    def test_pull_request_page_cap_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(fetch, "MAX_PR_PAGES", 2)
        fake = Fake([prs_page([pr(3)], "c1"), prs_page([pr(2)], "c2")])

        with pytest.raises(fetch.FetchError, match="exceeded 2 pages"):
            fetch.fetch_recent_pull_requests(fake, "o", "r", 10)

    def test_nested_connection_page_cap_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(fetch, "MAX_SUB_PAGES", 1)
        first = pr(5, conn([thread("t1", "cursor")], "tc"))
        more = {
            "repository": {"pullRequest": {"reviewThreads": conn([thread("t2", "cursor")], "td")}}
        }

        with pytest.raises(fetch.FetchError, match="exceeded 1 pages"):
            fetch.fetch_recent_pull_requests(Fake([prs_page([first]), more]), "o", "r", 1)


class TestMinerFetchExits:
    @pytest.fixture
    def api(self, monkeypatch: pytest.MonkeyPatch) -> Any:
        from scripts.github_core import api

        repo = type("Repo", (), {"owner": "o", "repo": "r"})()
        monkeypatch.setattr(api, "resolve_repo_params", lambda _o, _r: repo)
        return api

    def test_incomplete_pagination_exits_3(
        self, api: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        page = {"repository": {"pullRequests": {"pageInfo": {"hasNextPage": True}, "nodes": []}}}
        monkeypatch.setattr(api, "gh_graphql", lambda _q, _v: page)

        code = _load_miner().main(["--limit", "5", "--output", str(tmp_path / "d.json")])

        assert code == 3
        assert not (tmp_path / "d.json").exists()

    def test_auth_failure_exits_4(
        self, api: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def refuse(_q: str, _v: object) -> dict[str, Any]:
            raise RuntimeError("HTTP 401: Bad credentials")

        monkeypatch.setattr(api, "gh_graphql", refuse)
        monkeypatch.setattr(api, "is_auth_failure_text", lambda text: "401" in text)

        assert _load_miner().main(["--limit", "5", "--output", str(tmp_path / "d.json")]) == 4

    def test_gh_that_cannot_run_exits_3(
        self, api: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def missing(_q: str, _v: object) -> dict[str, Any]:
            raise FileNotFoundError("gh")

        monkeypatch.setattr(api, "gh_graphql", missing)

        assert _load_miner().main(["--limit", "5", "--output", str(tmp_path / "d.json")]) == 3

    def test_complete_read_writes_the_dump(
        self, api: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        pages = iter([{"rateLimit": {"cost": 1, "remaining": 5000}, **prs_page([pr(1)])}])
        monkeypatch.setattr(api, "gh_graphql", lambda _q, _v: next(pages))

        code = _load_miner().main(["--limit", "1", "--output", str(tmp_path / "d.json")])

        dump = json.loads((tmp_path / "d.json").read_text(encoding="utf-8"))
        assert code == 0
        assert [p["number"] for p in dump["pull_requests"]] == [1]
        assert dump["graphql_cost"] == 1


class TestMinerWriteFailure:
    def test_unwritable_output_exits_2(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from scripts.github_core import api

        repo = type("Repo", (), {"owner": "o", "repo": "r"})()
        monkeypatch.setattr(api, "resolve_repo_params", lambda _o, _r: repo)
        pages = iter([{"rateLimit": {"cost": 1, "remaining": 5000}, **prs_page([pr(1)])}])
        monkeypatch.setattr(api, "gh_graphql", lambda _q, _v: next(pages))
        blocker = tmp_path / "file"
        blocker.write_text("x", encoding="utf-8")

        code = _load_miner().main(["--limit", "1", "--output", str(blocker / "d.json")])

        assert code == 2
