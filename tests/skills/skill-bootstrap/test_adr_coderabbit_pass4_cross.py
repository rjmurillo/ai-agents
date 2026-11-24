"""Tests for the CodeRabbit pass 4 items that crossed module groups: A2, B17 and C11."""

from __future__ import annotations

import time

import adr_commits
import adr_locate
import adr_shape
import pytest

F3 = "`" * 3
ORIGIN = "https://github.com/o/r"
WHY = "Because the team already runs it in production and a second system needs a second on-call."


def _cut_fence_body() -> str:
    """An example fence holding a breaking line that closes only past the 64 KiB body cap."""
    filler = "x" * (adr_commits.MAX_BODY_CHARS + 100)
    return f"{WHY}\n\n{F3}\nexample\n\nBREAKING CHANGE: demo only\n{filler}\n{F3}"


def test_a_commit_fence_cut_by_the_cap_does_not_make_it_breaking() -> None:
    raw = (
        b"tree " + b"0" * 40 + b"\nauthor a <a@b> 1700000000 +0000\n\n"
        b"feat: adopt the new parser\n\n" + _cut_fence_body().encode()
    )

    record = adr_commits.parse_commit_object("1" * 40, raw)

    assert len(record.body) == adr_commits.MAX_BODY_CHARS and not record.breaking


def test_a_real_breaking_footer_is_still_read_from_the_whole_message() -> None:
    raw = (
        b"tree " + b"0" * 40 + b"\nauthor a <a@b> 1700000000 +0000\n\n"
        b"feat: adopt the new parser\n\nBody.\n\nBREAKING CHANGE: the old parser is gone."
    )

    assert adr_commits.parse_commit_object("1" * 40, raw).breaking


def test_a_pr_fence_cut_by_the_cap_does_not_make_it_breaking() -> None:
    row = {
        "number": 5,
        "title": "feat: adopt the new parser",
        "body": _cut_fence_body(),
        "url": f"{ORIGIN}/pull/5",
        "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada"},
    }

    (kept,) = adr_commits.select_prs([row], {}, ORIGIN)

    assert not kept.breaking and len(kept.body) == adr_commits.MAX_BODY_CHARS


@pytest.mark.parametrize(
    ("value", "kept"),
    [
        ("docs/My  Decisions.md", "docs/My  Decisions.md"),
        ("docs/a\nb.md", "docs/a b.md"),
        ("docs/a b.md", "docs/a b.md"),
    ],
)
def test_a_log_file_name_keeps_its_exact_spacing_on_one_line(value: str, kept: str) -> None:
    assert adr_locate.clean_source({"file": value})["file"] == kept


@pytest.mark.parametrize(
    ("subject", "bump"),
    [
        ("feat(runtime)!: Upgrade Python to 3.14", False),
        ("feat!: bump lodash to 4.17.21", False),
        ("feat(runtime): Upgrade Python to 3.14", True),
        ("chore(deps): bump lodash from 4.17.20 to 4.17.21", True),
    ],
)
def test_a_breaking_marker_keeps_a_bump_title_out_of_housekeeping(subject: str, bump: bool) -> None:
    assert adr_shape.is_release_or_bump_subject(subject) is bump
    if not bump:
        assert adr_shape.is_decision_commit(subject)


def test_an_api_address_in_html_url_is_incomplete_without_an_origin() -> None:
    row = {
        "number": 3,
        "title": "Adopt Rust for the parser",
        "body": WHY,
        "html_url": "https://api.github.com/repos/o/r/pulls/3",
        "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada"},
    }
    dropped: dict[str, int] = {}

    assert adr_commits.select_prs([row], dropped) == [] and dropped["pr_incomplete"] == 1


def test_an_ampersand_joined_url_list_before_prose_is_rejected_quickly() -> None:
    value = "https://a/b&" * 22 + " prose here"

    start = time.process_time()
    matched = adr_shape._REFERENCES_ONLY.search(value)

    assert matched is None and time.process_time() - start < 0.5


@pytest.mark.parametrize("value", ["#1, #2 and #3.", "12 & 13", "ABC-12; 13", "https://x?a=1&b=2"])
def test_reference_lists_still_count_as_references(value: str) -> None:
    assert adr_shape._REFERENCES_ONLY.search(value)
