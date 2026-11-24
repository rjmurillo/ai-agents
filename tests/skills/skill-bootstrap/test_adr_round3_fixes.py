"""Review round 3 tests: placeholder leak, PR export edge rows, escaping, and log file cap."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import adr_commits
import adr_locate
import adr_log
import adr_reason
import pytest
from adr_helpers import write

ORIGIN = "https://github.com/o/r"
WHY = "Because the team already runs it in production and a second system needs a second on-call."


def _row(number: int, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "number": number,
        "title": "Adopt gRPC instead of REST",
        "body": WHY,
        "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada"},
    }
    return {**base, **over}


def test_two_adjacent_urls_leave_no_placeholder_in_the_reason() -> None:
    body = (
        "We moved to gRPC because REST could not stream, see https://a.example https://b.example."
    )

    reason = adr_reason.extract_reason("Adopt gRPC", body)

    assert reason is not None
    assert adr_reason._URL_HOLE not in reason


def test_a_link_whose_url_holds_parentheses_is_reduced_to_its_text() -> None:
    body = (
        "We picked Raft, see [Raft](https://en.wikipedia.org/wiki/Raft_(algorithm)). "
        "It avoids split brain because leaders are elected."
    )

    reason = adr_reason.extract_reason("Adopt Raft", body)

    assert reason == "It avoids split brain because leaders are elected."


def test_an_unclosed_link_bracket_run_stays_fast() -> None:
    import time

    body = "We moved to gRPC because REST could not stream. " + "[" * 5900

    started = time.perf_counter()
    adr_reason.extract_reason("Adopt gRPC", body)

    assert time.perf_counter() - started < 0.05


def test_a_page_url_of_a_repository_named_repos_is_kept() -> None:
    dropped: dict[str, int] = {}
    url = "https://github.com/acme/repos/pull/3"

    rows = adr_commits.select_prs([_row(3, url=url)], dropped, "https://github.com/acme/repos")

    assert [row.url for row in rows] == [url]


def test_a_rest_api_pulls_url_is_still_not_the_page() -> None:
    dropped: dict[str, int] = {}
    api = "https://ghe.example.com/api/v3/repos/o/r/pulls/3"

    rows = adr_commits.select_prs([_row(3, url=api)], dropped, ORIGIN)

    assert rows == []
    assert dropped.get("pr_incomplete") == 1


def test_a_malformed_url_counts_as_one_incomplete_row_and_does_not_abort() -> None:
    dropped: dict[str, int] = {}

    rows = adr_commits.select_prs(
        [_row(1, url="https://[x/pull/1"), _row(2, url=f"{ORIGIN}/pull/2")], dropped, ORIGIN
    )

    assert [row.number for row in rows] == [2]
    assert dropped.get("pr_incomplete") == 1


@pytest.mark.parametrize(
    "subject", ["Merge pull request #² from a/b", "Merge pull request #٣ from a/b"]
)
def test_a_non_ascii_digit_in_a_merge_subject_is_not_a_pr_number(subject: str) -> None:
    record = adr_commits.CommitRecord("a" * 40, subject, "Ada", "2026-03-04T10:00:00Z", "")

    assert adr_commits.commit_pr_number(record, subject) is None


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("<!-- hide the rest", "\\<!-- hide the rest"),
        ("[x]: http://e.com", "\\[x]: http://e.com"),
        ("___", "\\___"),
        ("12. Adopt x", "12\\. Adopt x"),
        ("1) Adopt x", "1\\) Adopt x"),
        ("Use v1. now", "Use v1. now"),
        ("Adopt gRPC", "Adopt gRPC"),
    ],
)
def test_the_decision_line_escapes_every_leading_markdown_mark(title: str, expected: str) -> None:
    assert adr_locate._plain(title) == expected


def test_log_files_past_the_cap_are_counted_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adr_log, "MAX_LOG_FILES", 2)
    for n in range(4):
        write(tmp_path, f"docs/decisions-{n}-ledger.md", f"## D-{n}: Adopt x number {n}\n\nText.\n")

    entries, files, skipped = adr_log.read_log_entries(tmp_path)

    assert files == 4
    assert skipped == 2
    assert {rel for rel, _entry in entries} == {
        "docs/decisions-0-ledger.md",
        "docs/decisions-1-ledger.md",
    }
