"""Tests for the shared FailureClassifier (REQ-048 TASK-002).

Each class pins the REQ-048 acceptance criterion in its name. The criteria
are quoted from the 2026-11-01 amendment.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.failure_classifier import (
    DENIAL_MARKERS,
    FINGERPRINT_MAX_CHARS,
    FailureEvent,
    canonical_input,
    canonicalize_input_text,
    classify,
    events_from_records,
    failure_fingerprint,
)

TEST = "pytest tests/a.py"


def ev(tool: str, ok: bool, error: str = "", cmd: str | None = None, target: str | None = None):
    return FailureEvent.build(tool=tool, ok=ok, error=error, input=cmd, target=target)


class TestAC29Fingerprint:
    def test_six_steps(self) -> None:
        line = "  Error AT line 12 in commit abcdef1234   and   0xDEADBEEF\nsecond line"
        assert failure_fingerprint(" Bash ", line) == "bash|error at line N in commit H and H"

    def test_first_non_blank_line(self) -> None:
        assert failure_fingerprint("Bash", "\n \n boom \nlater") == "bash|boom"

    def test_words_and_numbers_are_not_hex(self) -> None:
        assert failure_fingerprint("Bash", "file defaced 12345678") == "bash|file defaced N"

    def test_line_is_capped(self) -> None:
        key = failure_fingerprint("Bash", "x" * 500)
        assert key is not None and len(key) == len("bash|") + FINGERPRINT_MAX_CHARS

    @pytest.mark.parametrize("error", ["", "   \n\t"])
    def test_no_error_text_has_no_fingerprint(self, error: str) -> None:
        assert failure_fingerprint("Bash", error) is None


class TestAC01AC02ErrorKinds:
    def test_errored_result_is_a_tool_error(self) -> None:
        assert classify([ev("Bash", False, "exit code 1")]).tool_error == 1

    @pytest.mark.parametrize("marker", DENIAL_MARKERS)
    def test_denial_marker_is_a_permission_denial_not_a_tool_error(self, marker: str) -> None:
        signals = classify([ev("Bash", False, f"Action {marker.upper()} by policy")])
        assert (signals.permission_denial, signals.tool_error) == (1, 0)

    def test_successes_count_neither(self) -> None:
        signals = classify([ev("Bash", True)] * 3)
        assert (signals.tool_error, signals.permission_denial) == (0, 0)


class TestAC03AC04FailedRetry:
    def test_same_key_and_fingerprint_counts_each_match_after_the_first(self) -> None:
        assert classify([ev("Bash", False, "boom", TEST)] * 3).failed_retry == 2

    def test_not_back_to_back_still_counts(self) -> None:
        events = [
            ev("Bash", False, "boom", TEST),
            ev("Read", True, cmd="x"),
            ev("Bash", False, "boom", TEST),
        ]
        assert classify(events).failed_retry == 1

    def test_success_for_the_key_between_resets(self) -> None:
        events = [
            ev("Bash", False, "boom", TEST),
            ev("Bash", True, cmd=TEST),
            ev("Bash", False, "boom", TEST),
        ]
        assert classify(events).failed_retry == 0

    def test_different_fingerprint_does_not_count(self) -> None:
        events = [ev("Bash", False, "boom", TEST), ev("Bash", False, "bang", TEST)]
        assert classify(events).failed_retry == 0

    def test_success_for_another_key_does_not_reset(self) -> None:
        events = [
            ev("Bash", False, "boom", TEST),
            ev("Bash", True, cmd="ls"),
            ev("Bash", False, "boom", TEST),
        ]
        assert classify(events).failed_retry == 1

    def test_keyless_failures_are_not_retries(self) -> None:
        # A retry is the same call again; without `input` there is no call to match.
        assert classify([ev("Bash", False, "boom")] * 3).failed_retry == 0


class TestAC30ProgressReset:
    def test_successful_ls_between_test_runs_resets_nothing(self) -> None:
        events = [
            ev("Bash", False, "boom", TEST),
            ev("Bash", True, cmd="ls"),
            ev("Bash", False, "boom", TEST),
        ]
        assert classify(events).repeat_totals() == {"bash|boom": 2}

    def test_fixed_make_build_keeps_the_npm_test_loop(self) -> None:
        events = [ev("Bash", False, "exit code 1", "npm test")] * 2
        events += [
            ev("Bash", False, "exit code 1", "make build"),
            ev("Bash", True, cmd="make build"),
        ]
        events += [ev("Bash", False, "exit code 1", "npm test")]
        signals = classify(events)
        assert signals.repeat_totals() == {"bash|exit code N": 3}
        assert list(signals.tally) == [("bash", "npm test")]

    def test_keyless_success_resets_nothing(self) -> None:
        events = [
            ev("Bash", False, "boom", TEST),
            ev("Bash", True),
            ev("Bash", False, "boom", TEST),
        ]
        assert classify(events).repeat_totals() == {"bash|boom": 2}

    def test_reset_also_removes_the_keys_churn_entries(self) -> None:
        events = [ev("Edit", True, target="a.py"), ev("Bash", False, "x", TEST)] * 2
        events += [ev("Bash", True, cmd=TEST)]
        assert classify(events).churn_totals() == {}


class TestAC31FailedEdits:
    def test_old_string_not_found_three_times(self) -> None:
        bad = ev("Edit", False, "old_string not found", "e1", "a.py")
        signals = classify([bad] * 3)
        assert signals.repeat_totals() == {"edit|old_string not found": 3}
        assert signals.failed_retry == 2


class TestAC32ChurnCycles:
    def test_cycles_sharing_a_fingerprint(self) -> None:
        events = [ev("Edit", True, target="./src//a.py"), ev("Bash", False, "x failed", TEST)] * 3
        signals = classify(events)
        assert signals.churn_totals() == {"src/a.py": {"bash|x failed": 3}}
        assert signals.churned_targets(3) == {"src/a.py": ("bash|x failed", 3)}

    def test_devins_case_reports_no_churn(self) -> None:
        cycle = [
            ev("Edit", True, target="a.py"),
            ev("Bash", True, cmd="pytest tests/a.py"),
            ev("Bash", False, "FAILED test_b", "pytest tests/b.py"),
        ]
        assert classify(cycle * 3).churn_totals() == {}

    def test_keyless_success_ends_the_cycle(self) -> None:
        cycle = [ev("Edit", True, target="a.py"), ev("Read", True), ev("Bash", False, "x", TEST)]
        assert classify(cycle * 3).churn_totals() == {}

    def test_failed_edit_closes_no_cycle(self) -> None:
        events = [ev("Edit", True, target="a.py"), ev("Edit", False, "nope", target="b.py")]
        events += [ev("Bash", False, "x", TEST)]
        assert classify(events).churn_totals() == {"a.py": {"bash|x": 1}}

    def test_edit_without_target_opens_none(self) -> None:
        assert classify([ev("Edit", True), ev("Bash", False, "x", TEST)] * 3).churn_totals() == {}

    def test_edit_leaves_other_pending_cycles(self) -> None:
        events = [
            ev("Edit", True, target="a.py"),
            ev("Write", True, target="b.py"),
            ev("Bash", False, "x", TEST),
        ]
        assert classify(events).churn_totals() == {"a.py": {"bash|x": 1}, "b.py": {"bash|x": 1}}

    def test_unfingerprinted_failure_does_not_close(self) -> None:
        events = [
            ev("Edit", True, target="a.py"),
            ev("Bash", False, ""),
            ev("Bash", False, "x", TEST),
        ]
        assert classify(events).churn_totals() == {"a.py": {"bash|x": 1}}

    def test_several_edits_before_one_failure_are_one_cycle(self) -> None:
        events = [ev("Edit", True, target="a.py")] * 3 + [ev("Bash", False, "x", TEST)]
        assert classify(events).churn_totals() == {"a.py": {"bash|x": 1}}


class TestAC37Unfingerprinted:
    def test_counted_as_tool_error_and_unfingerprinted_only(self) -> None:
        signals = classify([ev("Bash", False, "", TEST)] * 3)
        assert (signals.tool_error, signals.unfingerprinted) == (3, 3)
        assert (signals.failed_retry, signals.repeat_totals()) == (0, {})


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


class TestAC39InputCanonicalization:
    def test_json_document_gets_the_ac38_form(self) -> None:
        text = ' {"timeout": 5,  "command": "ls"} '
        assert canonicalize_input_text(text) == canonical_input({"command": "ls", "timeout": 5})

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("  pytest tests/a.py  ", "pytest tests/a.py"),
            ("{not json", "{not json"),
            ("[" * 100_000, "[" * 100_000),
        ],
    )
    def test_other_text_is_used_as_given_after_trimming(self, text: str, expected: str) -> None:
        assert canonicalize_input_text(text) == expected

    def test_scalar_json_round_trips(self) -> None:
        assert canonicalize_input_text('"ls"') == '"ls"'
