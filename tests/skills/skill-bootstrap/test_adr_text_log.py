"""Tests for adr_text and adr_log: dates, links, slugs, and decision-log files (P12, P14).

Ports tests/fetchers_docs-decision-log.test.ts of align-cli (MIT, Copyright (c) 2026 Align
Tech Ltd, see LICENSE-align) at the entry level: upstream reads them through fetchDocsItems and
builds source URLs, which this port does not. The date cases port the real-calendar-day rule of
tests/fetchers_docs-adr-dates.test.ts D4c (isoOrNull). The other date cases read ADR headers or
git history, and no command here dates an existing ADR, so they are not ported.
"""

from __future__ import annotations

from pathlib import Path

import adr_log
import adr_text
import pytest
from adr_helpers import write

LEDGER = """# Defect ledger
id: D-001 · status: test · review_by: 2027-04-27 · modified: 2026-10-27
Retry the webhook three times before dead-lettering it.
id: D-002 | status: retired | modified: 2026-09-01
Poll the queue every five seconds instead of using push delivery.
"""
NUMBERED = """# Decision log
## D17 - Use Postgres for the graph
We chose Postgres over a graph database because the team already runs it.
D181: Never store raw message text in the payload column
Decided: 2026-03-04
Raw text stays in the source system; we keep a pointer only.
"""


def _entries(text: str) -> list[adr_log.LogEntry]:
    return adr_log.split_decision_log(text)


def test_a_ledger_splits_into_one_entry_per_id_line() -> None:
    first, second = _entries(LEDGER)
    assert (first.id, second.id) == ("D-001", "D-002")
    assert "Retry the webhook three times" in first.text and "Poll the queue" not in first.text


def test_a_ledger_entry_is_titled_by_its_text_not_its_fields_and_falls_back_to_the_id() -> None:
    first, second, third = _entries(LEDGER + "\nid: D-003 · status: test\n")
    assert first.title == "Retry the webhook three times before dead-lettering it."
    assert second.title == "Poll the queue every five seconds instead of using push delivery."
    assert third.title == "D-003"


def test_an_entry_is_dated_from_modified_and_left_undated_when_no_field_parses() -> None:
    text = (
        LEDGER + "\nid: D-004 · modified: soon\nSomething was decided here with no usable date.\n"
    )
    entries = _entries(text)
    assert adr_log.entry_date(entries[0].text) == "2026-10-27"
    assert adr_log.entry_date(entries[2].text) is None


def test_the_date_fields_are_read_in_order_and_a_bad_day_is_skipped() -> None:
    assert adr_log.entry_date("id: D1 | date: 2026-02-30 | decided: 2026-03-04") == "2026-03-04"
    assert adr_log.entry_date("D1: x\nmodified: 2026-05-06\ndate: 2026-01-02") == "2026-01-02"
    assert adr_log.entry_date("D1: x\n- decided: 2026-03-04\n") == "2026-03-04"


def test_a_numbered_log_splits_on_headings_and_id_lines_and_dates_from_decided() -> None:
    first, second = _entries(NUMBERED)
    assert [first.id, second.id] == ["D17", "D181"]
    assert first.title == "D17 - Use Postgres for the graph"
    assert "team already runs it" in first.text
    assert second.title == "D181: Never store raw message text in the payload column"
    assert adr_log.entry_date(second.text) == "2026-03-04"


def test_an_entry_with_no_id_keeps_its_heading_and_has_no_id() -> None:
    (entry,) = _entries(
        "# Decisions\n\n## Use pnpm everywhere\n\nWe use pnpm in every package so locks agree.\n"
    )
    assert (entry.id, entry.title) == (None, "Use pnpm everywhere")


def test_the_listed_names_are_found_at_the_root_and_in_docs(tmp_path: Path) -> None:
    names = ["DECISION_LOG.md", "DECISION-LOG.md", "docs/DECISIONS.md", "docs/team-LEDGER.md"]
    for index, name in enumerate(names):
        write(tmp_path, name, f"D{index + 1}: Keep this decision in the log file\n")
    write(tmp_path, "README.md", "D9: not a log\n")
    write(tmp_path, "docs/guide.md", "D9: not a log\n")
    assert adr_log.find_log_files(tmp_path) == sorted(names)
    entries = adr_log.read_log_entries(tmp_path)
    assert sorted(entry.id or "" for _file, entry in entries) == ["D1", "D2", "D3", "D4"]


def test_nothing_under_a_dot_folder_is_read(tmp_path: Path) -> None:
    write(tmp_path, "DECISIONS.md", "D1: A real decision the user wrote by hand\n")
    write(tmp_path, ".align/decisions.md", "D2: Written by a tool and must not be read back\n")
    write(tmp_path, ".align/DECISIONS.md", "D3: Written by a tool and must not be read back\n")
    assert adr_log.find_log_files(tmp_path) == ["DECISIONS.md"]


def test_a_log_with_no_recognisable_entries_gives_nothing() -> None:
    assert _entries("# Decisions\n\nWe will write these down one day, when we have time.\n") == []


def test_a_retired_entry_is_kept_with_its_status_text() -> None:
    retired = next(entry for entry in _entries(LEDGER) if entry.id == "D-002")
    assert "status: retired" in retired.text


def test_a_fenced_example_with_an_id_line_stays_inside_its_entry() -> None:
    text = (
        "D1: Log entries use this format\n\n```\nD999: example only, not a decision\n"
        "## Not a heading\n```\n\nD2: Entries are append-only in the file\n"
    )
    entries = _entries(text)
    assert [entry.id for entry in entries] == ["D1", "D2"]
    assert "D999: example only" in entries[0].text


@pytest.mark.parametrize(
    ("heading", "title"),
    [
        ("D17 - Use Postgres | status: superseded", "D17 - Use Postgres"),
        ("D18 - Support Linux | macOS | status: accepted", "D18 - Support Linux | macOS"),
        (
            "D19 - Reference | https://example.com/spec | status: accepted",
            "D19 - Reference | https://example.com/spec",
        ),
        ("D20 - Support Linux | macOS ##", "D20 - Support Linux | macOS"),
        ("D21 - Support C#", "D21 - Support C#"),
    ],
)
def test_key_value_fields_leave_a_heading_title_but_stay_in_the_text(
    heading: str, title: str
) -> None:
    (entry,) = _entries(f"## {heading}\n\nThe graph lives in Postgres for now.\n")
    assert entry.title == title
    if "status:" in heading:
        assert "status:" in entry.text


def test_a_short_entry_with_a_recognised_id_is_kept() -> None:
    assert [entry.title for entry in _entries("D1: Use PostgreSQL\n")] == ["D1: Use PostgreSQL"]


def test_a_heading_with_no_id_and_a_short_body_is_not_an_entry() -> None:
    assert _entries("## Misc\n\nshort\n") == []


@pytest.mark.parametrize(
    ("value", "day"),
    [
        ("2024-02-29", "2024-02-29"),
        ("2026-10-27T10:00:00Z", "2026-10-27"),
        ("2024-02-30", None),
        ("2023-02-29", None),
        ("2024-13-45", None),
        ("12", None),
        ("March", None),
        ("", None),
        (None, None),
        (20241231, None),
    ],
)
def test_a_date_is_kept_only_when_it_is_a_real_calendar_day(value: object, day: str | None) -> None:
    assert adr_text.iso_day(value) == day


def test_urls_are_read_whole_with_sentence_punctuation_dropped() -> None:
    text = (
        "See https://github.com/o/r/issues/123. And [x](https://a.example/p) or "
        "<https://b.example/q>, plus git://c.example/r/commit/abc1234!"
    )
    assert adr_text.urls_in(text) == {
        "https://github.com/o/r/issues/123",
        "https://a.example/p",
        "https://b.example/q",
        "git://c.example/r/commit/abc1234",
    }


def test_hash_tokens_are_whole_hex_words_of_seven_or_more() -> None:
    tokens = adr_text.hash_tokens(
        "a1b2c3d (A1B2C3D4E) abc123 x1234567y 1234567890abcdef0 deadbeef_"
    )
    assert tokens == {"a1b2c3d", "a1b2c3d4e", "1234567890abcdef0"}


def test_issue_numbers_need_a_whole_token_hash() -> None:
    assert adr_text.issue_numbers("#12 and (#34), a#5, /#6, &#7; #8x #99.") == {12, 34, 99}


def test_a_log_id_is_found_only_as_a_whole_word() -> None:
    assert adr_text.word_present("D-001", "see d-001.")
    assert not adr_text.word_present("D-001", "see D-0010")
    assert not adr_text.word_present("D1", "ID1 and D1-2")
    assert adr_text.word_present("D1", "(D1)")


def test_sanitize_drops_control_bytes_and_cuts_to_the_limit() -> None:
    assert adr_text.sanitize("a\x00b\x1b[0m\r\nc\x7f\td", 6) == "ab[0m\n"
    assert adr_text.sanitize("keep\ttabs\nand newlines") == "keep\ttabs\nand newlines"
