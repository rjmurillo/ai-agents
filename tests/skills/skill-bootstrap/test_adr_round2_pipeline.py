"""Review round 2 tests for the scan pipeline: items 4, 5 and 6."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import adr_commits
import adr_scan
from adr_helpers import commit, git, new_repo, write

WHY = "Because the team already runs it in production and a second system needs a second on-call."
ORIGIN = "https://github.com/o/r"


def _repo(tmp_path: Path) -> Path:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-first.md", "# 1. First\n\n## Status\n\nAccepted\n")
    commit(repo, "Initial work")
    git(repo, "remote", "add", "origin", f"{ORIGIN}.git")
    return repo


def _pr(number: int, title: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "number": number,
        "title": title,
        "body": WHY,
        "url": f"{ORIGIN}/pull/{number}",
        "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada"},
    }
    return {**base, **over}


def _scan(repo: Path, prs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = adr_scan.scan(repo, "HEAD", 300, None, prs)
    return payload


def _merge(repo: Path, number: int, title: str, body: str = "") -> str:
    """A ``--no-ff`` merge whose branch commit is one the filters drop. Returns the merge SHA."""
    branch = f"feat-{number}"
    git(repo, "checkout", "-q", "-b", branch)
    commit(repo, f"work for {number}", rel=f"w{number}.txt")
    git(repo, "checkout", "-q", "main")
    messages = ["-m", f"Merge pull request #{number} from o/{branch}", "-m", title]
    if body:
        messages += ["-m", body]
    git(repo, "merge", "--no-ff", "-q", *messages, branch)
    return git(repo, "rev-parse", "HEAD").strip()


# ---------------------------------------------------------------------------
# Item 4: the page URL of a raw GitHub REST pull object
# ---------------------------------------------------------------------------


def _rest_pr(number: int, title: str, **over: Any) -> dict[str, Any]:
    """A pull object as the GitHub REST API returns it: ``url`` is the API endpoint."""
    row = _pr(number, title, **over)
    row["url"] = f"https://api.github.com/repos/o/r/pulls/{number}"
    row["html_url"] = f"{ORIGIN}/pull/{number}"
    return row


def test_a_rest_pull_object_with_both_url_fields_is_this_repositorys_row(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    payload = _scan(repo, [_rest_pr(12, "Adopt Postgres instead of MySQL")])
    assert payload["dropped"]["pr_other_repo"] == 0
    assert [c["id"] for c in payload["candidates"]] == ["pr-12"]
    assert payload["candidates"][0]["source"]["url"] == f"{ORIGIN}/pull/12"


def test_an_api_url_with_no_page_url_is_incomplete_not_another_repository(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    row = _rest_pr(12, "Adopt Postgres instead of MySQL")
    del row["html_url"]
    payload = _scan(repo, [row])
    assert payload["dropped"]["pr_incomplete"] == 1
    assert payload["dropped"]["pr_other_repo"] == 0 and payload["candidates"] == []


def test_a_url_with_a_repos_path_is_not_a_page_url() -> None:
    dropped: dict[str, int] = {}
    ghes = _pr(
        3, "Adopt gRPC instead of REST", url="https://ghe.example.com/api/v3/repos/o/r/pulls/3"
    )
    rows = adr_commits.select_prs([ghes], dropped, "https://ghe.example.com/o/r")
    assert rows == [] and dropped == {"pr_incomplete": 1}


def test_a_page_url_in_the_url_field_still_works() -> None:
    dropped: dict[str, int] = {}
    rows = adr_commits.select_prs([_pr(4, "Adopt gRPC instead of REST")], dropped, ORIGIN)
    assert [row.url for row in rows] == [f"{ORIGIN}/pull/4"]


def test_html_url_wins_over_a_page_url_in_the_url_field() -> None:
    dropped: dict[str, int] = {}
    both = _pr(5, "Adopt gRPC instead of REST", html_url=f"{ORIGIN}/pull/5?x=1")
    rows = adr_commits.select_prs([both], dropped, ORIGIN)
    assert [row.url for row in rows] == [f"{ORIGIN}/pull/5?x=1"]


# ---------------------------------------------------------------------------
# Item 5: a merge commit is covered by its pull request number
# ---------------------------------------------------------------------------


def test_a_no_ff_merge_and_its_pr_row_without_a_merge_sha_give_one_decision(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _merge(repo, 12, "Adopt the circuit breaker for all outbound calls")
    payload = _scan(repo, [_pr(12, "Adopt the circuit breaker for all outbound calls")])
    assert [c["id"] for c in payload["candidates"]] == ["pr-12"]
    assert payload["dropped"]["covered_by_pr"] == 1


def test_a_merge_commit_of_a_pr_that_is_not_in_the_export_is_still_a_candidate(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    merge = _merge(repo, 12, "Adopt the circuit breaker for all outbound calls")
    payload = _scan(repo, [_pr(30, "Adopt the circuit breaker for all outbound calls")])
    assert sorted(c["id"] for c in payload["candidates"]) == sorted(["pr-30", f"c-{merge[:7]}"])
    assert payload["dropped"]["covered_by_pr"] == 0


def test_a_merge_commit_is_covered_by_the_merge_sha_as_before(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    merge = _merge(repo, 12, "Adopt the circuit breaker for all outbound calls")
    row = _pr(12, "Adopt the circuit breaker for all outbound calls", merge_commit_sha=merge)
    payload = _scan(repo, [row])
    assert [c["id"] for c in payload["candidates"]] == ["pr-12"]


# ---------------------------------------------------------------------------
# Item 6: the breaking signal of a covered commit moves to its pull request
# ---------------------------------------------------------------------------


def test_a_breaking_squash_commit_gives_its_non_breaking_pr_the_signal(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    squash = commit(repo, "feat!: drop support for the v1 API (#12)")
    row = _pr(12, "feat: drop support for the v1 API", merge_commit_sha=squash)
    payload = _scan(repo, [row])
    assert [c["id"] for c in payload["candidates"]] == ["pr-12"]
    assert payload["candidates"][0]["signals"] == ["breaking-change"]


def test_a_breaking_merge_commit_covered_by_number_gives_its_pr_the_signal(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _merge(repo, 12, "feat!: drop support for the v1 API")
    payload = _scan(repo, [_pr(12, "feat: drop support for the v1 API")])
    assert [c["id"] for c in payload["candidates"]] == ["pr-12"]
    assert payload["candidates"][0]["signals"] == ["breaking-change"]


def test_a_breaking_pr_keeps_one_signal_when_its_commit_is_breaking_too(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    squash = commit(repo, "feat!: drop support for the v1 API (#12)")
    row = _pr(12, "feat!: drop support for the v1 API", merge_commit_sha=squash)
    payload = _scan(repo, [row])
    assert payload["candidates"][0]["signals"] == ["breaking-change"]


def test_a_non_breaking_covered_commit_adds_no_signal(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    squash = commit(repo, "feat: drop support for the v1 API (#12)")
    row = _pr(12, "feat: drop support for the v1 API", merge_commit_sha=squash)
    payload = _scan(repo, [row])
    assert [c["id"] for c in payload["candidates"]] == ["pr-12"]
    assert payload["candidates"][0]["signals"] == []


def test_a_breaking_commit_covered_by_another_pr_leaves_the_rest_alone(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    squash = commit(repo, "feat!: drop support for the v1 API (#12)")
    rows = [
        _pr(12, "feat: drop support for the v1 API", merge_commit_sha=squash),
        _pr(13, "Adopt Postgres instead of MySQL"),
    ]
    payload = _scan(repo, rows)
    signals = {c["id"]: c["signals"] for c in payload["candidates"]}
    assert signals == {"pr-12": ["breaking-change"], "pr-13": []}
