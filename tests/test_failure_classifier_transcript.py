"""Tests for the FailureClassifier transcript adapter (REQ-048 AC-38)."""

from __future__ import annotations

from typing import Any

import pytest

from scripts.failure_classifier import FailureEvent, canonical_input, classify, events_from_records


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
            == '{"a":"é","b":1}'
        )


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

    def test_missing_or_null_input_has_no_progress_key(self) -> None:
        bare = {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash"}]},
        }
        records = [
            bare,
            result("t1", "boom", True),
            use("t2", "Bash", None),
            result("t2", "boom", True),
        ]
        events = events_from_records(records)
        assert [e.progress_key for e in events] == [None, None]
        assert classify(events).failed_retry == 0
