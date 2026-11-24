"""Tests for the CodeRabbit pass 4 items that crossed module groups: A2, B17 and C11."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import adr_commits
import adr_locate
import adr_log
import adr_reason
import adr_shape
import adr_write
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


def test_no_reader_sees_a_partial_file_before_it_is_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "docs" / "0002-x.md"
    data = b"# 2. X\n" * 1000
    real_link = os.link
    seen: list[tuple[bool, bytes]] = []

    def watching(source: str, name: Path) -> None:
        seen.append((Path(name).exists(), Path(source).read_bytes()))
        real_link(source, name)

    monkeypatch.setattr(os, "link", watching)
    adr_write.create_new(target, data)

    assert seen == [(False, data)] and target.read_bytes() == data
    assert [p.name for p in target.parent.iterdir()] == ["0002-x.md"]


def test_without_hard_links_the_file_is_written_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "0002-x.md"

    def no_links(source: str, name: Path) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "link", no_links)
    adr_write.create_new(target, b"body")

    assert target.read_bytes() == b"body" and [p.name for p in tmp_path.iterdir()] == ["0002-x.md"]


def test_a_failed_publish_leaves_neither_the_target_nor_a_temporary_file(tmp_path: Path) -> None:
    target = tmp_path / "0002-x.md"
    data: Any = "not bytes"

    with pytest.raises(TypeError):
        adr_write.create_new(target, data)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_a_published_file_has_the_mode_open_would_give(tmp_path: Path) -> None:
    target = tmp_path / "0002-x.md"
    umask = os.umask(0)
    os.umask(umask)

    adr_write.create_new(target, b"body")

    assert target.stat().st_mode & 0o777 == 0o666 & ~umask


@pytest.mark.parametrize(
    "line",
    [
        "fixes https://example.com/path,a",
        "fixes https://a/b,https://c/d",
        "fixes https://x/y,o/r#4",
        "fixes https://a/b?x=1&y=2, https://c/d",
    ],
)
def test_a_url_keeps_a_comma_that_starts_no_other_reference(line: str) -> None:
    assert adr_shape.FIXES_ONLY.match(line)


@pytest.mark.parametrize(
    "value",
    [
        "https://x,1,1," * 14 + " prose",
        "https://x,AB-1," * 14 + " prose",
        "https://x,a," * 16 + " prose",
    ],
)
def test_url_commas_never_make_the_reference_list_backtrack(value: str) -> None:
    start = time.process_time()
    matched = adr_shape._REFERENCES_ONLY.search(value)

    assert matched is None and time.process_time() - start < 0.5


def test_a_peer_section_after_a_ledger_is_not_the_last_records_reason() -> None:
    log = (
        "# Decision log\n\n- D-1: Adopt trunk-based development for every repo\n"
        "- D-2: Use Renovate for dependency updates\n\n## How to add a decision\n\n"
        "Add one line per decision because reviewers read this file first.\n"
    )

    entries = adr_log.split_decision_log(log)

    assert [entry.id for entry in entries] == ["D-1", "D-2", None]
    assert "reviewers read" not in entries[1].text


def test_a_subsection_under_a_heading_decision_stays_with_it() -> None:
    log = "# Log\n\n## D-3 - Keep Postgres\n\n### Rationale\n\nBecause the team knows it.\n"

    (entry,) = [e for e in adr_log.split_decision_log(log) if e.id]

    assert entry.id == "D-3" and "team knows it" in entry.text


def test_a_github_merge_time_with_z_is_read_on_every_python() -> None:
    assert adr_commits._merged_day("2026-01-01T00:00:00Z") == "2026-01-01"


def test_a_long_issue_list_footer_line_costs_flat_memory() -> None:
    body = "Body.\n\nBREAKING CHANGE: x\n\na " + "#b " * 400_000 + "!"

    start = time.process_time()
    result = adr_reason.breaking_change("feat: x", body)

    assert result is False and time.process_time() - start < 2.0
