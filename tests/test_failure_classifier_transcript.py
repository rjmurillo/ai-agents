"""Tests for the FailureClassifier transcript adapter (REQ-048 AC-38)."""

from __future__ import annotations

from typing import Any

import pytest

from scripts.failure_classifier import (
    FailureEvent,
    canonical_input,
    classify,
    events_from_records,
    stop_feedback_count,
)


def use(use_id: str, name: str, tool_input: Any, sidechain: bool = False) -> dict[str, Any]:
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {
            "content": [{"type": "tool_use", "id": use_id, "name": name, "input": tool_input}]
        },
    }


def result(
    use_id: str, content: Any, is_error: bool | None = None, sidechain: bool = False
) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": use_id, "content": content}
    if is_error is not None:
        block["is_error"] = is_error
    return {"type": "user", "isSidechain": sidechain, "message": {"content": [block]}}


class TestAC38TranscriptAdapter:
    def test_pair_becomes_one_event(self) -> None:
        records = [use("t1", "Bash", {"command": "ls", "timeout": 5}), result("t1", "boom", True)]
        assert events_from_records(records) == [
            FailureEvent(
                tool="bash",
                ok=False,
                error="boom",
                input='{"command":"ls","timeout":5}',
                target=None,
            )
        ]

    def test_is_error_absent_means_success(self) -> None:
        events = events_from_records(
            [use("t1", "Read", {"file_path": "a.py"}), result("t1", "text")]
        )
        assert events[0].ok is True
        assert events[0].target is None  # Read is not an edit tool

    def test_edit_target_from_file_path_or_path(self) -> None:
        records = [
            use("t1", "Edit", {"file_path": "./src/a.py", "old_string": "x"}),
            result("t1", "ok"),
            use("t2", "apply_patch", {"path": "src\\b.py"}),
            result("t2", "ok"),
            use("t3", "NotebookEdit", {"notebook_path": "nb/c.ipynb", "new_source": "x"}),
            result("t3", "ok"),
        ]
        targets = [e.target for e in events_from_records(records)]
        assert targets == ["src/a.py", "src/b.py", "nb/c.ipynb"]

    def test_list_content_joins_text_blocks(self) -> None:
        content = [
            {"type": "text", "text": "first"},
            {"type": "image"},
            {"type": "text", "text": "second"},
        ]
        events = events_from_records([use("t1", "Bash", {}), result("t1", content, True)])
        assert events[0].error == "first\nsecond"

    def test_sidechain_records_are_excluded(self) -> None:
        records = [
            use("t1", "Bash", {}, sidechain=True),
            result("t1", "boom", True, sidechain=True),
        ]
        assert events_from_records(records) == []

    def test_unpaired_blocks_emit_nothing(self) -> None:
        records = [use("t1", "Bash", {}), result("t9", "orphan", True), {"type": "summary"}, "junk"]
        assert events_from_records(records) == []

    def test_canonical_input_is_order_independent(self) -> None:
        assert (
            canonical_input({"b": 1, "a": "é"})
            == canonical_input({"a": "é", "b": 1})
            == '{"a":"\\u00e9","b":1}'
        )

    def test_canonical_input_escapes_non_ascii_outside_the_bmp(self) -> None:
        assert canonical_input({"k": "\U0001f600"}) == '{"k":"\\ud83d\\ude00"}'

    def test_transcript_input_with_non_ascii_is_escaped_in_the_event(self) -> None:
        events = events_from_records([use("t1", "Bash", {"command": "echo é"}), result("t1", "x")])
        assert events[0].input == '{"command":"echo \\u00e9"}'

    def test_bash_command_input_is_a_derived_check(self) -> None:
        records = [
            use("t1", "Bash", {"command": "pytest tests/a.py"}),
            result("t1", "boom", True),
            use("t2", "Bash", {"command": "ls"}),
            result("t2", "ok"),
            use("t3", "Read", {"file_path": "a.py"}),
            result("t3", "text"),
        ]
        events = events_from_records(records)
        assert [e.check for e in events] == [None, None, None]
        assert [e.is_check for e in events] == [True, False, False]

    def test_edit_then_non_check_then_failing_check_reports_churn(self) -> None:
        records: list[dict[str, Any]] = []
        for n in range(3):
            records += [
                use(f"e{n}", "Edit", {"file_path": "a.py", "old_string": "x"}),
                result(f"e{n}", "ok"),
                use(f"l{n}", "Bash", {"command": "ls"}),
                result(f"l{n}", "a.py"),
                use(f"t{n}", "Bash", {"command": "pytest tests/a.py"}),
                result(f"t{n}", "FAILED test_a", True),
            ]
        signals = classify(events_from_records(records))
        assert signals.churn_totals() == {"a.py": {"bash|failed test_a": 3}}


class TestAC38RepeatedRecords:
    def test_repeated_use_and_result_emit_one_event(self) -> None:
        # A resumed session repeats earlier records verbatim.
        pair = [use("t1", "Bash", {"command": "pytest"}), result("t1", "boom", True)]
        events = events_from_records(pair + pair + [result("t1", "boom", True)])
        assert len(events) == 1
        assert classify(events).failed_retry == 0

    def test_request_blob_copies_are_ignored(self) -> None:
        pair = [use("t1", "Bash", {"command": "pytest"}), result("t1", "boom", True)]
        blob = {
            "type": "api-request-blob",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t2",
                        "name": "Bash",
                        "input": {"command": "pytest"},
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "t2",
                        "content": "boom",
                        "is_error": True,
                    },
                ]
            },
        }
        assert len(events_from_records([blob, *pair, blob])) == 1

    def test_use_in_user_record_or_result_in_assistant_record_is_ignored(self) -> None:
        wrong_use = use("t1", "Bash", {"command": "ls"})
        wrong_use["type"] = "user"
        wrong_result = result("t2", "boom", True)
        wrong_result["type"] = "assistant"
        records = [wrong_use, result("t1", "boom", True), use("t2", "Bash", {}), wrong_result]
        assert events_from_records(records) == []

    def test_distinct_ids_still_pair(self) -> None:
        records = [
            use("t1", "Bash", {"command": "pytest"}),
            result("t1", "boom", True),
            use("t2", "Bash", {"command": "pytest"}),
            result("t2", "boom", True),
        ]
        assert classify(events_from_records(records)).failed_retry == 1


class TestAC38MalformedRecords:
    @pytest.mark.parametrize(
        "record",
        [
            {"type": "user", "message": {"content": "plain user text"}},
            {"type": "assistant", "message": "not an object"},
            {"type": "assistant"},
            {"type": "user", "message": {"content": [5, "x", None]}},
        ],
    )
    def test_shapes_without_blocks_emit_nothing(self, record: dict[str, Any]) -> None:
        records = [use("t1", "Bash", {}), record]
        assert events_from_records(records) == []

    @pytest.mark.parametrize("content", [None, 5, {"text": "x"}])
    def test_non_text_result_content_is_an_empty_error(self, content: object) -> None:
        events = events_from_records([use("t1", "Bash", {}), result("t1", content, True)])
        assert [(e.ok, e.error) for e in events] == [(False, "")]
        assert classify(events).unfingerprinted == 1

    def test_missing_input_has_no_progress_key(self) -> None:
        bare = {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash"}]},
        }
        bare2 = {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "id": "t2", "name": "Bash"}]},
        }
        records = [bare, result("t1", "boom", True), bare2, result("t2", "boom", True)]
        events = events_from_records(records)
        assert [e.progress_key for e in events] == [None, None]
        assert classify(events).failed_retry == 0

    def test_explicit_null_input_keys_as_null(self) -> None:
        # AC-38 serializes null as `null`; consumer A keys the string "null"
        # the same way (AC-39), so the two adapters agree.
        records = [
            use("t1", "Bash", None),
            result("t1", "boom", True),
            use("t2", "Bash", None),
            result("t2", "boom", True),
        ]
        events = events_from_records(records)
        assert [e.progress_key for e in events] == [("bash", "null"), ("bash", "null")]
        assert classify(events).failed_retry == 1


FEEDBACK = "Stop hook feedback: run the retrospective"


def user(content: Any, sidechain: bool = False, **extra: Any) -> dict[str, Any]:
    return {"type": "user", "isSidechain": sidechain, "message": {"content": content}, **extra}


def text_block(text: str) -> dict[str, str]:
    return {"type": "text", "text": text}


class TestStopFeedbackCount:
    def test_empty_input_is_zero(self) -> None:
        assert stop_feedback_count([]) == 0

    def test_string_content_counts(self) -> None:
        assert stop_feedback_count([user(FEEDBACK)]) == 1

    def test_text_block_content_counts(self) -> None:
        assert stop_feedback_count([user([text_block(FEEDBACK)])]) == 1

    def test_leading_whitespace_is_stripped(self) -> None:
        assert (
            stop_feedback_count([user("  \n" + FEEDBACK), user([text_block("\t" + FEEDBACK)])]) == 2
        )

    def test_empty_first_block_still_counts(self) -> None:
        assert stop_feedback_count([user([text_block(""), text_block(FEEDBACK)])]) == 1

    def test_prefix_must_open_the_text(self) -> None:
        assert stop_feedback_count([user("note: " + FEEDBACK), user("stop hook feedback: x")]) == 0

    def test_sidechain_is_ignored(self) -> None:
        assert stop_feedback_count([user(FEEDBACK, sidechain=True)]) == 0

    def test_tool_result_user_records_are_ignored(self) -> None:
        records = [
            result("t1", FEEDBACK),
            user(FEEDBACK, toolUseResult={"stdout": "x"}),
            user([{"type": "tool_result", "tool_use_id": "t2", "content": FEEDBACK}]),
        ]
        assert stop_feedback_count(records) == 0

    def test_assistant_records_are_ignored(self) -> None:
        record = {"type": "assistant", "message": {"content": [text_block(FEEDBACK)]}}
        assert stop_feedback_count([record]) == 0

    @pytest.mark.parametrize("record", ["text", 3, None, [], {"type": "user"}, user(None), user(7)])
    def test_malformed_records_are_skipped(self, record: Any) -> None:
        assert stop_feedback_count([record]) == 0

    def test_counts_every_match(self) -> None:
        assert (
            stop_feedback_count([user(FEEDBACK), user("hello"), user([text_block(FEEDBACK)])]) == 2
        )
