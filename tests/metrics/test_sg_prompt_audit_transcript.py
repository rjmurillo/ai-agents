"""Tests for process_transcript_file in scripts/metrics/sg_prompt_audit_parse.py
(#5856, REQ-3): the per-transcript-file parsing pipeline (positive per kind,
skip/failure/malformed-line handling).

Split out of the original monolithic ``test_sg_prompt_audit.py`` under the
taste-lints file-size gate; fixture prompt/transcript builders live in
``tests/metrics/sg_prompt_audit_helpers.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.metrics import sg_prompt_audit_parse as parse_mod
from scripts.metrics.sg_prompt_audit_models import Locator, UsageTotals
from tests.metrics.sg_prompt_audit_helpers import (
    USAGE_1,
    assistant_entry,
    diff_text,
    investigate_prompt,
    iter2_prompt,
    jsonl,
    other_entry,
    refute_prompt,
    successful_session,
    user_entry,
    write_transcript,
)

# --- process_transcript_file: positive per kind ---------------------------------


def test_process_transcript_file_investigate_end_to_end(tmp_path: Path) -> None:
    diff = diff_text([("src/foo.py", "+line one\n+line two\n")])
    lines = successful_session(investigate_prompt(diff))
    path = write_transcript(tmp_path, "proj-a", "sess1.jsonl", lines)

    record, skipped = parse_mod.process_transcript_file(path, "proj-a")

    assert skipped == 0
    assert record is not None
    assert record.kind == "investigate"
    assert record.locator == Locator(project="proj-a", file="sess1.jsonl", line=2)
    assert record.cwd == "/repo"
    assert record.started_at == "2026-09-20T00:00:00.000Z"
    assert record.ended_at == "2026-09-20T00:00:02.000Z"
    assert record.latency_s == pytest.approx(2.0)
    assert record.diff_bytes == len(diff.encode("utf-8"))
    assert len(record.blocks) == 1
    assert record.blocks[0].path == "src/foo.py"
    assert record.cap.per_file_truncated == 0
    assert record.checkout_note is False
    assert record.assistant_turns == 2
    assert record.usage == UsageTotals(300, 11, 55, 60)
    assert record.first_turn_usage == UsageTotals(**USAGE_1)
    assert record.succeeded is True
    assert record.failure is None


def test_process_transcript_file_iter2_end_to_end(tmp_path: Path) -> None:
    diff = diff_text([("src/foo.py", "+line one\n")])
    lines = successful_session(iter2_prompt(diff))
    path = write_transcript(tmp_path, "proj-a", "sess2.jsonl", lines)

    record, skipped = parse_mod.process_transcript_file(path, "proj-a")

    assert skipped == 0
    assert record is not None
    assert record.kind == "iter2"
    assert record.diff_bytes == len(diff.encode("utf-8"))


def test_process_transcript_file_refute_end_to_end(tmp_path: Path) -> None:
    diff = diff_text([("src/foo.py", "+line one\n")])
    lines = successful_session(refute_prompt(diff))
    path = write_transcript(tmp_path, "proj-a", "sess3.jsonl", lines)

    record, skipped = parse_mod.process_transcript_file(path, "proj-a")

    assert skipped == 0
    assert record is not None
    assert record.kind == "refute"
    assert record.diff_bytes == len(diff.encode("utf-8"))
    assert record.checkout_note is False


def test_process_transcript_file_list_form_message_content(tmp_path: Path) -> None:
    diff = diff_text([("src/foo.py", "+line one\n")])
    text = investigate_prompt(diff)
    entries = [
        user_entry([{"type": "text", "text": text}]),
        assistant_entry(
            "2026-09-20T00:00:01Z", usage=USAGE_1, tool_names=("StructuredOutput",)
        ),
    ]
    path = write_transcript(tmp_path, "proj-a", "sess4.jsonl", entries)

    record, _ = parse_mod.process_transcript_file(path, "proj-a")

    assert record is not None
    assert record.kind == "investigate"
    assert record.succeeded is True


# --- process_transcript_file: skip/failure/malformed paths ----------------------


def test_process_transcript_file_skips_non_review_session(tmp_path: Path) -> None:
    entries = [user_entry("What is the capital of France?")]
    path = write_transcript(tmp_path, "proj-a", "sess5.jsonl", entries)

    record, skipped = parse_mod.process_transcript_file(path, "proj-a")

    assert record is None
    assert skipped == 0


def test_process_transcript_file_skips_file_with_no_user_entry(tmp_path: Path) -> None:
    entries = [other_entry("2026-09-20T00:00:00Z")]
    path = write_transcript(tmp_path, "proj-a", "sess6.jsonl", entries)

    record, skipped = parse_mod.process_transcript_file(path, "proj-a")

    assert record is None
    assert skipped == 0


def test_process_transcript_file_counts_malformed_lines(tmp_path: Path) -> None:
    diff = diff_text([("a.py", "+x\n")])
    lines: list[object] = [
        "{not valid json",
        user_entry(investigate_prompt(diff)),
        "also not valid json{{{",
        assistant_entry(
            "2026-09-20T00:00:01Z", usage=USAGE_1, tool_names=("StructuredOutput",)
        ),
    ]
    path = write_transcript(tmp_path, "proj-a", "sess7.jsonl", lines)

    record, skipped = parse_mod.process_transcript_file(path, "proj-a")

    assert record is not None
    assert skipped == 2


def test_process_transcript_file_only_counts_malformed_lines_read_before_stopping(
    tmp_path: Path,
) -> None:
    lines: list[object] = [
        "{broken before}",
        user_entry("not a review prompt at all"),
        "{broken after, never read}",
    ]
    path = write_transcript(tmp_path, "proj-a", "sess8.jsonl", lines)

    record, skipped = parse_mod.process_transcript_file(path, "proj-a")

    assert record is None
    assert skipped == 1


def test_process_transcript_file_skips_blank_lines_without_counting_them(
    tmp_path: Path,
) -> None:
    diff = diff_text([("a.py", "+x\n")])
    text = jsonl(
        [
            "",
            json.dumps(user_entry(investigate_prompt(diff))),
            "",
            json.dumps(
                assistant_entry(
                    "2026-09-20T00:00:01Z", usage=USAGE_1, tool_names=("StructuredOutput",)
                )
            ),
        ]
    )
    project_dir = tmp_path / "proj-a"
    project_dir.mkdir(parents=True)
    path = project_dir / "sess9.jsonl"
    path.write_text(text, encoding="utf-8")

    record, skipped = parse_mod.process_transcript_file(path, "proj-a")

    assert record is not None
    assert skipped == 0


def test_process_transcript_file_counts_non_object_json_as_malformed(
    tmp_path: Path,
) -> None:
    diff = diff_text([("a.py", "+x\n")])
    lines: list[object] = [
        "[1, 2, 3]",
        user_entry(investigate_prompt(diff)),
    ]
    path = write_transcript(tmp_path, "proj-a", "sess10.jsonl", lines)

    record, skipped = parse_mod.process_transcript_file(path, "proj-a")

    assert record is not None
    assert skipped == 1


def test_process_transcript_file_finds_first_user_entry_past_leading_entries(
    tmp_path: Path,
) -> None:
    diff = diff_text([("a.py", "+x\n")])
    entries = [
        other_entry("2026-09-20T00:00:00Z"),
        other_entry("2026-09-20T00:00:00Z"),
        user_entry(investigate_prompt(diff)),
    ]
    path = write_transcript(tmp_path, "proj-a", "sess11.jsonl", entries)

    record, _ = parse_mod.process_transcript_file(path, "proj-a")

    assert record is not None
    assert record.locator.line == 3


def test_process_transcript_file_ignores_non_assistant_entries_after_first_user(
    tmp_path: Path,
) -> None:
    """Covers an entry with no timestamp key, and a post-first-user entry
    that is neither "user" nor "assistant" (e.g. a queue-operation)."""
    diff = diff_text([("a.py", "+x\n")])
    entries: list[object] = [
        user_entry(investigate_prompt(diff)),
        {"type": "queue-operation"},  # no "timestamp" key at all
        assistant_entry(
            "2026-09-20T00:00:01Z", usage=USAGE_1, tool_names=("StructuredOutput",)
        ),
    ]
    path = write_transcript(tmp_path, "proj-a", "sess14.jsonl", entries)

    record, _ = parse_mod.process_transcript_file(path, "proj-a")

    assert record is not None
    assert record.assistant_turns == 1
    assert record.succeeded is True
    assert record.ended_at == "2026-09-20T00:00:01Z"


def test_process_transcript_file_no_assistant_turns_is_failure(tmp_path: Path) -> None:
    diff = diff_text([("a.py", "+x\n")])
    entries = [user_entry(investigate_prompt(diff))]
    path = write_transcript(tmp_path, "proj-a", "sess12.jsonl", entries)

    record, _ = parse_mod.process_transcript_file(path, "proj-a")

    assert record is not None
    assert record.assistant_turns == 0
    assert record.succeeded is False
    assert record.failure == "no_assistant"
    assert record.first_turn_usage is None


def test_process_transcript_file_assistant_without_structured_output_is_failure(
    tmp_path: Path,
) -> None:
    diff = diff_text([("a.py", "+x\n")])
    entries = [
        user_entry(investigate_prompt(diff)),
        assistant_entry("2026-09-20T00:00:01Z", usage=USAGE_1, text="no findings tool called"),
    ]
    path = write_transcript(tmp_path, "proj-a", "sess13.jsonl", entries)

    record, _ = parse_mod.process_transcript_file(path, "proj-a")

    assert record is not None
    assert record.assistant_turns == 1
    assert record.succeeded is False
    assert record.failure == "no_structured_output"


