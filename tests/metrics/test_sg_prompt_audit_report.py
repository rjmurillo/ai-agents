"""Tests for build_report and its helpers in scripts/metrics/sg_prompt_audit.py
(#5856, REQ-3): grouping, window filtering, and date-bound parsing.

Split out of the original monolithic ``test_sg_prompt_audit.py`` under the
taste-lints file-size gate; fixture prompt/transcript builders live in
``tests/metrics/sg_prompt_audit_helpers.py``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts.metrics import sg_prompt_audit as audit
from scripts.metrics.sg_prompt_audit_models import CapCounts, Locator, SessionRecord, UsageTotals
from tests.metrics.sg_prompt_audit_helpers import (
    USAGE_1,
    assistant_entry,
    diff_text,
    investigate_prompt,
    iter2_prompt,
    refute_prompt,
    successful_session,
    user_entry,
    write_transcript,
)

# --- build_report / summarize: grouping ------------------------------------------


def test_build_report_groups_repeated_identical_diffs(tmp_path: Path) -> None:
    diff = diff_text([("a.py", "+shared content\n")])
    session_one = successful_session(
        investigate_prompt(diff), ts_start="2026-09-20T00:00:00Z", cwd="/repo1"
    )
    session_two = successful_session(
        investigate_prompt(diff), ts_start="2026-09-20T01:00:00Z", cwd="/repo2"
    )
    write_transcript(tmp_path, "proj-a", "s1.jsonl", session_one)
    write_transcript(tmp_path, "proj-b", "s2.jsonl", session_two)

    report = audit.build_report(tmp_path, since=None, until=None, top=20)

    assert report.sessions_examined == 2
    assert len(report.repeated_diffs) == 1
    group = report.repeated_diffs[0]
    assert group.count == 2
    assert group.bytes == len(diff.encode("utf-8"))
    assert group.redundant_bytes == group.bytes
    assert group.distinct_cwds == 2
    assert group.kinds == ["investigate"]
    assert group.time_span_seconds == pytest.approx(3600.0)


def test_build_report_does_not_group_a_single_diff(tmp_path: Path) -> None:
    diff = diff_text([("a.py", "+unique\n")])
    session = successful_session(investigate_prompt(diff))
    write_transcript(tmp_path, "proj-a", "s1.jsonl", session)

    report = audit.build_report(tmp_path, since=None, until=None, top=20)

    assert report.repeated_diffs == []


def test_build_report_groups_repeated_block_across_projects(tmp_path: Path) -> None:
    shared_block = ("shared/util.py", "+def helper(): pass\n")
    diff_one = diff_text([shared_block, ("a.py", "+only in session one\n")])
    diff_two = diff_text([shared_block, ("b.py", "+only in session two\n")])
    session_one = successful_session(investigate_prompt(diff_one))
    session_two = successful_session(investigate_prompt(diff_two))
    write_transcript(tmp_path, "proj-a", "s1.jsonl", session_one)
    write_transcript(tmp_path, "proj-b", "s2.jsonl", session_two)

    report = audit.build_report(tmp_path, since=None, until=None, top=20)

    assert report.repeated_diffs == []  # the two diffs differ, only the block repeats
    assert len(report.repeated_blocks) == 1
    block_group = report.repeated_blocks[0]
    assert block_group.path == "shared/util.py"
    assert block_group.sessions == 2
    assert block_group.distinct_projects == 2
    assert block_group.redundant_bytes == block_group.bytes


def test_build_report_top_n_truncates_but_grand_totals_cover_every_group(
    tmp_path: Path,
) -> None:
    big_diff = diff_text([("a.py", "+" + "x" * 100 + "\n")])
    small_diff = diff_text([("b.py", "+y\n")])
    big_session = successful_session(investigate_prompt(big_diff))
    small_session = successful_session(investigate_prompt(small_diff))
    for i in range(2):
        write_transcript(tmp_path, "proj-a", f"big{i}.jsonl", big_session)
    for i in range(2):
        write_transcript(tmp_path, "proj-a", f"small{i}.jsonl", small_session)

    report = audit.build_report(tmp_path, since=None, until=None, top=1)

    assert len(report.repeated_diffs) == 1
    assert report.repeated_diffs[0].bytes == len(big_diff.encode("utf-8"))
    expected_grand = len(big_diff.encode("utf-8")) + len(small_diff.encode("utf-8"))
    assert report.grand_redundant_bytes_diffs == expected_grand
    assert report.grand_redundant_tokens_diffs == expected_grand // 4


def test_build_report_iter2_cache_only_covers_iter2_sessions_with_assistant_turns(
    tmp_path: Path,
) -> None:
    diff = diff_text([("a.py", "+x\n")])
    write_transcript(
        tmp_path, "proj-a", "iter2.jsonl", successful_session(iter2_prompt(diff))
    )
    write_transcript(
        tmp_path, "proj-a", "investigate.jsonl", successful_session(investigate_prompt(diff))
    )
    write_transcript(
        tmp_path,
        "proj-a",
        "iter2-no-turns.jsonl",
        [user_entry(iter2_prompt(diff))],
    )

    report = audit.build_report(tmp_path, since=None, until=None, top=20)

    assert len(report.iter2_cache) == 1
    entry = report.iter2_cache[0]
    assert entry.locator.file == "iter2.jsonl"
    assert entry.cache_read_input_tokens == USAGE_1["cache_read_input_tokens"]
    assert entry.cache_creation_input_tokens == USAGE_1["cache_creation_input_tokens"]


def test_build_report_lists_failures_with_reason(tmp_path: Path) -> None:
    diff = diff_text([("a.py", "+x\n")])
    write_transcript(
        tmp_path, "proj-a", "no-assistant.jsonl", [user_entry(investigate_prompt(diff))]
    )
    write_transcript(
        tmp_path,
        "proj-a",
        "no-structured.jsonl",
        [
            user_entry(investigate_prompt(diff)),
            assistant_entry("2026-09-20T00:00:01Z", usage=USAGE_1, text="no tool call"),
        ],
    )

    report = audit.build_report(tmp_path, since=None, until=None, top=20)

    reasons = {(f.locator.file, f.reason) for f in report.failures}
    assert reasons == {
        ("no-assistant.jsonl", "no_assistant"),
        ("no-structured.jsonl", "no_structured_output"),
    }


def test_build_report_counts_by_kind_and_prompt_bytes(tmp_path: Path) -> None:
    diff = diff_text([("a.py", "+x\n")])
    investigate_text = investigate_prompt(diff)
    refute_text = refute_prompt(diff)
    write_transcript(
        tmp_path, "proj-a", "s1.jsonl", successful_session(investigate_text)
    )
    write_transcript(tmp_path, "proj-a", "s2.jsonl", successful_session(refute_text))

    report = audit.build_report(tmp_path, since=None, until=None, top=20)

    assert report.counts_by_kind == {"investigate": 1, "refute": 1}
    expected_bytes = len(investigate_text.encode("utf-8")) + len(refute_text.encode("utf-8"))
    assert report.total_prompt_bytes == expected_bytes
    assert report.estimated_tokens == expected_bytes // 4
    assert report.token_estimate_method == "bytes_div_4"


def test_diff_group_entry_span_zero_when_fewer_than_two_timestamps() -> None:
    def _record(started_at: str) -> SessionRecord:
        return SessionRecord(
            locator=Locator(project="p", file="f.jsonl", line=1),
            kind="investigate",
            cwd="/repo",
            started_at=started_at,
            ended_at=started_at,
            latency_s=0.0,
            prompt_bytes=1,
            prompt_sha256="x",
            diff_bytes=1,
            diff_sha256="y",
            blocks=(),
            path_order_sha256="z",
            cap=CapCounts(0, 0, 0),
            checkout_note=False,
            assistant_turns=0,
            usage=UsageTotals(0, 0, 0, 0),
            first_turn_usage=None,
            succeeded=False,
            failure="no_assistant",
        )

    members = [_record(""), _record("")]

    group = audit._diff_group_entry("hash", members)

    assert group.time_span_seconds == 0.0


# --- window filtering -------------------------------------------------------------


def test_in_window_true_when_no_bounds_set() -> None:
    assert audit._in_window("2026-09-20T00:00:00Z", None, None) is True


def test_in_window_false_when_started_at_missing_and_bounds_set() -> None:
    assert audit._in_window("", date(2026, 9, 1), None) is False


def test_in_window_respects_since_and_until_boundaries() -> None:
    since = date(2026, 9, 10)
    until = date(2026, 9, 20)
    assert audit._in_window("2026-09-10T00:00:00Z", since, until) is True  # on since
    assert audit._in_window("2026-09-20T23:59:59Z", since, until) is True  # on until
    assert audit._in_window("2026-09-09T23:59:59Z", since, until) is False  # before since
    assert audit._in_window("2026-09-21T00:00:00Z", since, until) is False  # after until


def test_build_report_excludes_sessions_outside_window_but_still_counts_skipped_lines(
    tmp_path: Path,
) -> None:
    diff = diff_text([("a.py", "+x\n")])
    lines: list[object] = [
        "{malformed}",
        *successful_session(investigate_prompt(diff), ts_start="2026-01-01T00:00:00Z"),
    ]
    write_transcript(tmp_path, "proj-a", "old.jsonl", lines)
    write_transcript(
        tmp_path,
        "proj-a",
        "new.jsonl",
        successful_session(investigate_prompt(diff), ts_start="2026-09-20T00:00:00Z"),
    )
    report = audit.build_report(
        tmp_path, since=date(2026, 9, 1), until=date(2026, 9, 30), top=20
    )

    assert report.sessions_examined == 1
    assert report.skipped_lines == 1


# --- date parsing -----------------------------------------------------------------


def test_parse_date_bound_returns_none_for_none() -> None:
    assert audit._parse_date_bound(None) is None


def test_parse_date_bound_parses_iso_date() -> None:
    assert audit._parse_date_bound("2026-09-20") == date(2026, 9, 20)


def test_parse_date_bound_raises_on_malformed_date() -> None:
    with pytest.raises(ValueError):
        audit._parse_date_bound("not-a-date")


