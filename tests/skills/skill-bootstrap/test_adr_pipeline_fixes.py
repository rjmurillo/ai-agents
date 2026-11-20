"""Tests for the scan pipeline: E3 with pull requests, foreign exports, merge promotion.

Covers the decision flow in ``adr_scan.scan``: which pull requests cover a commit, which
export rows belong to this repository, and how a promoted merge is judged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import adr_commits
import adr_scan
from adr_helpers import commit, git, new_repo, write

WHY = "Because the team already runs it in production and a second system needs a second on-call."


def _repo(tmp_path: Path, origin: str | None = "https://github.com/o/r.git") -> Path:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-first.md", "# 1. First\n\n## Status\n\nAccepted\n")
    commit(repo, "Initial work")
    if origin:
        git(repo, "remote", "add", "origin", origin)
    return repo


def _pr(number: int, title: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "number": number,
        "title": title,
        "body": WHY,
        "url": f"https://github.com/o/r/pull/{number}",
        "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada"},
    }
    return {**base, **over}


def _scan(repo: Path, prs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return adr_scan.scan(repo, "HEAD", 300, None, prs)


# ---------------------------------------------------------------------------
# Item 12: E3 and the pull request that covers a commit
# ---------------------------------------------------------------------------


def test_a_breaking_squash_commit_and_its_pull_request_give_one_decision(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    squash = commit(repo, "feat!: drop the v1 API (#12)")
    payload = _scan(repo, [_pr(12, "feat!: drop the v1 API", merge_commit_sha=squash)])
    assert [c["id"] for c in payload["candidates"]] == ["pr-12"]
    assert payload["candidates"][0]["signals"] == ["breaking-change"]
    assert payload["dropped"]["covered_by_pr"] == 1
    assert payload["dropped"]["pr_not_decision_shaped"] == 0


def test_a_pull_request_that_is_dropped_covers_no_commit(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    commit(repo, "feat!: drop the v1 API (#15)")
    payload = _scan(repo, [_pr(15, "feat: drop the v1 API")])
    assert payload["dropped"]["pr_not_decision_shaped"] == 1
    assert [c["kind"] for c in payload["candidates"]] == ["commit"]
    assert payload["candidates"][0]["signals"] == ["breaking-change"]
    assert payload["dropped"]["covered_by_pr"] == 0


def test_a_breaking_pull_request_with_a_mechanical_title_stays_out(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    payload = _scan(repo, [_pr(16, "chore!: drop the v1 API tables")])
    assert payload["candidates"] == []
    assert payload["dropped"]["pr_not_decision_shaped"] == 1


def test_a_breaking_pull_request_keeps_its_signal_when_the_title_is_decision_shaped(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    payload = _scan(repo, [_pr(17, "feat!: switch to gRPC for every internal call")])
    assert payload["candidates"][0]["signals"] == ["breaking-change"]


def test_a_pull_request_with_a_footer_marker_is_a_candidate_without_a_decision_shaped_title(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    body = f"{WHY}\n\nBREAKING CHANGE: the v1 routes are gone."
    payload = _scan(repo, [_pr(18, "Remove the legacy router module", body=body)])
    assert [c["id"] for c in payload["candidates"]] == ["pr-18"]
    assert payload["candidates"][0]["signals"] == ["breaking-change"]


# ---------------------------------------------------------------------------
# Item 13: the export is checked against this repository
# ---------------------------------------------------------------------------


def test_a_pull_request_of_another_repository_is_dropped_and_covers_no_commit(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    squash = commit(repo, f"Adopt Postgres instead of MySQL (#13)\n\n{WHY}\n")
    foreign = _pr(
        13,
        "Adopt Postgres instead of MySQL",
        url="https://github.com/other/repo/pull/13",
        merge_commit_sha=squash,
    )
    payload = _scan(repo, [foreign])
    assert payload["dropped"]["pr_other_repo"] == 1
    assert payload["dropped"]["covered_by_pr"] == 0
    assert [c["id"] for c in payload["candidates"]] == [f"c-{squash[:7]}"]
    assert payload["examined"]["prs"] == 1


def test_the_origin_is_compared_without_regard_to_case(tmp_path: Path) -> None:
    repo = _repo(tmp_path, origin="https://github.com/O/R.git")
    payload = _scan(repo, [_pr(12, "Adopt Postgres instead of MySQL")])
    assert payload["dropped"]["pr_other_repo"] == 0
    assert [c["id"] for c in payload["candidates"]] == ["pr-12"]


def test_without_a_known_origin_every_export_row_is_kept(tmp_path: Path) -> None:
    repo = _repo(tmp_path, origin=None)
    foreign = _pr(13, "Adopt Postgres instead of MySQL", url="https://github.com/x/y/pull/13")
    payload = _scan(repo, [foreign])
    assert payload["dropped"]["pr_other_repo"] == 0
    assert [c["id"] for c in payload["candidates"]] == ["pr-13"]


def test_select_prs_counts_a_row_from_another_repository() -> None:
    dropped: dict[str, int] = {}
    rows = adr_commits.select_prs(
        [
            _pr(1, "Adopt gRPC instead of REST"),
            _pr(2, "Adopt gRPC", url="https://github.com/x/y/pull/2"),
        ],
        dropped,
        "https://github.com/o/r",
    )
    assert [row.number for row in rows] == [1]
    assert dropped == {"pr_other_repo": 1}


def test_select_prs_without_a_base_keeps_the_old_behavior() -> None:
    dropped: dict[str, int] = {}
    rows = adr_commits.select_prs(
        [_pr(2, "Adopt gRPC", url="https://github.com/x/y/pull/2")], dropped
    )
    assert [row.number for row in rows] == [2] and dropped == {}


# ---------------------------------------------------------------------------
# Item 14: a promoted merge is judged as upstream judges it
# ---------------------------------------------------------------------------


def _merge(repo: Path, number: int, title: str, body: str = "") -> None:
    branch = f"feat-{number}"
    git(repo, "checkout", "-q", "-b", branch)
    commit(repo, f"work for {number}", rel=f"w{number}.txt")
    git(repo, "checkout", "-q", "main")
    messages = ["-m", f"Merge pull request #{number} from o/{branch}", "-m", title]
    if body:
        messages += ["-m", body]
    git(repo, "merge", "--no-ff", "-q", *messages, branch)


def test_a_promoted_merge_with_a_one_off_title_and_no_reason_is_dropped(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _merge(repo, 5, "Rename queue helpers to follow the new convention")
    payload = _scan(repo)
    assert payload["candidates"] == []
    assert payload["dropped"]["no_rationale"] == 1


def test_a_promoted_merge_whose_title_is_not_a_one_off_is_kept_without_a_body_reason(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _merge(repo, 6, "Adopt the circuit breaker for all outbound calls")
    payload = _scan(repo)
    assert [c["title"] for c in payload["candidates"]] == [
        "Adopt the circuit breaker for all outbound calls"
    ]
    assert payload["dropped"]["no_rationale"] == 0


def test_a_promoted_merge_with_a_one_off_title_is_kept_when_its_body_states_a_reason(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _merge(repo, 7, "Rename queue helpers to follow the new convention", WHY)
    payload = _scan(repo)
    assert [c["title"] for c in payload["candidates"]] == [
        "Rename queue helpers to follow the new convention"
    ]


def test_the_original_merge_line_is_not_a_reason() -> None:
    body = "Merge pull request #5 from o/feat-5\n\nBecause the old helper names were confusing."
    assert adr_commits.without_merge_lines(body) == "\nBecause the old helper names were confusing."
    assert adr_commits.without_merge_lines("Merge branch 'x' into y") == ""
    assert (
        adr_commits.without_merge_lines("Merge the queues into one") == "Merge the queues into one"
    )
