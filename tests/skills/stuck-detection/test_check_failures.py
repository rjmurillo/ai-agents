#!/usr/bin/env python3
"""Tests for the check-failures signals and event parsing (failure_loops.py)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from stuck_failure_events import TEST_CMD, fail, fc, kinds, mod, ok, run

check_failures = mod.check_failures
parse_events = mod.parse_events
failure_fingerprint = fc.failure_fingerprint
build_failure_nudge = mod.build_failure_nudge
EventError = mod.EventError


class TestFailureFingerprint:
    def test_numbers_and_hashes_collapse(self) -> None:
        a = failure_fingerprint("Bash", "error at line 12 in commit abcdef1234\nmore")
        b = failure_fingerprint("bash", "Error at line 99 in commit 0123456789ab")
        assert a == b == "bash|error at line N in commit H"

    def test_hex_needs_a_digit_and_a_letter(self) -> None:
        assert failure_fingerprint("Bash", "file defaced") == "bash|file defaced"
        assert failure_fingerprint("Bash", "pid 12345678") == "bash|pid N"

    def test_uses_first_nonblank_line(self) -> None:
        assert failure_fingerprint("Bash", "\n\n  boom  \nsecond") == "bash|boom"

    def test_different_errors_differ(self) -> None:
        assert failure_fingerprint("Bash", "no such file") != failure_fingerprint(
            "Bash", "permission denied"
        )

    @pytest.mark.parametrize("error", ["", "   \n\t\n"])
    def test_no_error_text_has_no_fingerprint(self, error: str) -> None:
        assert failure_fingerprint("Bash", error) is None

    def test_caps_length(self) -> None:
        key = failure_fingerprint("Bash", "x" * 500)
        assert key is not None
        assert len(key) == len("bash|") + fc.FINGERPRINT_MAX_CHARS


class TestFailureRepeat:
    def test_three_identical_failures_trip(self) -> None:
        result = run([fail("Bash", "pytest: command not found")] * 3)
        assert result["stuck"] is True
        assert result["signals"] == [
            {
                "signal": "failure-repeat",
                "fingerprint": "bash|pytest: command not found",
                "count": 3,
            }
        ]
        assert "the same bash failure 3 times" in result["nudge"]

    def test_two_failures_do_not_trip(self) -> None:
        result = run([fail("Bash", "boom")] * 2)
        assert result["stuck"] is False
        assert result["signals"] == []
        assert (result["events_total"], result["events_checked"]) == (2, 2)
        assert result["counts"]["tool_error"] == 2

    def test_distinct_failures_do_not_trip(self) -> None:
        events = [fail("Bash", "a broke"), fail("Bash", "b broke"), fail("Bash", "c broke")]
        assert run(events)["stuck"] is False

    def test_failures_without_error_text_never_combine(self) -> None:
        assert run([{"tool": "Bash", "ok": False}] * 5)["stuck"] is False

    def test_same_error_on_different_tools_does_not_combine(self) -> None:
        events = [fail("Bash", "boom"), fail("Read", "boom"), fail("Grep", "boom")]
        assert run(events)["stuck"] is False

    def test_successes_never_count(self) -> None:
        assert run([ok("Bash")] * 10)["stuck"] is False

    def test_window_drops_old_failures(self) -> None:
        result = run([fail("Bash", "boom")] * 3 + [ok("Read")] * 20)
        assert result["stuck"] is False
        assert (result["events_total"], result["events_checked"]) == (23, 20)

    def test_custom_threshold(self) -> None:
        events = [fail("Bash", "boom")] * 3
        assert run(events, repeat_threshold=4)["stuck"] is False
        assert run(events + [fail("Bash", "boom")], repeat_threshold=4)["stuck"] is True

    def test_sorted_most_frequent_first(self) -> None:
        events = [fail("Bash", "b")] * 3 + [fail("Bash", "a")] * 4
        assert [s["fingerprint"] for s in run(events)["signals"]] == ["bash|a", "bash|b"]

    def test_matching_success_clears_the_count(self) -> None:
        events = [fail("Bash", "boom", TEST_CMD)] * 2 + [ok("Bash", command=TEST_CMD)]
        events += [fail("Bash", "boom", TEST_CMD)] * 2
        assert run(events)["stuck"] is False

    def test_unrelated_success_of_same_tool_does_not_clear(self) -> None:
        events = [fail("Bash", "boom", TEST_CMD)] * 2 + [ok("Bash", command="ls")]
        events += [fail("Bash", "boom", TEST_CMD)]
        assert kinds(run(events)) == ["failure-repeat"]

    def test_success_without_input_does_not_clear(self) -> None:
        events = [fail("Bash", "boom")] * 2 + [ok("Bash")] + [fail("Bash", "boom")]
        assert kinds(run(events)) == ["failure-repeat"]


class TestEditChurn:
    def cycle(self, error: str = "test_x failed", target: str = "src/a.py") -> list[dict[str, Any]]:
        # AC-32: the edit, then the failing check that closes its cycle.
        return [ok("Edit", target), fail("Bash", error, TEST_CMD)]

    def test_three_cycles_same_failure_trip(self) -> None:
        events = self.cycle("e1 failed") * 3
        assert run(events, repeat_threshold=10)["signals"] == [
            {
                "signal": "edit-churn",
                "target": "src/a.py",
                "fingerprint": "bash|eN failed",
                "count": 3,
            }
        ]

    @pytest.mark.parametrize("between", ["Bash", "Read"])
    def test_successful_non_check_between_edit_and_failure_leaves_the_cycle_open(
        self, between: str
    ) -> None:
        # AC-32 "Closing on success": only a check ends a cycle. An `ls` or a
        # read between the edit and the failing test leaves it open, so churn fires.
        events = [ok("Edit", "src/a.py"), ok(between, command="ls"), fail("Bash", "x", TEST_CMD)]
        assert run(events * 3, repeat_threshold=10)["signals"] == [
            {"signal": "edit-churn", "target": "src/a.py", "fingerprint": "bash|x", "count": 3}
        ]

    def test_devins_case_reports_no_churn(self) -> None:
        cycle = [
            ok("Edit", "a.py"),
            ok("Bash", command="pytest tests/a.py"),
            fail("Bash", "FAILED test_b", "pytest tests/b.py"),
        ]
        assert run(cycle * 3, repeat_threshold=10)["signals"] == []

    def test_keyless_successful_check_ends_the_cycle(self) -> None:
        check = {"tool": "Bash", "ok": True, "check": True}
        events = [ok("Edit", "a.py"), check, fail("Bash", "x", TEST_CMD)]
        assert run(events * 3, repeat_threshold=10)["signals"] == []

    def test_ls_and_git_status_leave_the_cycle_open(self) -> None:
        events = [
            ok("Edit", "a.py"),
            ok("Bash", command="ls"),
            ok("Bash", command="git status"),
            fail("Bash", "x", "pytest tests/a.py"),
        ]
        signals = run(events * 3, repeat_threshold=10)["signals"]
        assert [(s["target"], s["count"]) for s in signals] == [("a.py", 3)]

    def test_failed_cat_then_passing_check_records_no_outcome(self) -> None:
        events = [
            ok("Edit", "a.py"),
            fail("Bash", "cat: missing.txt: No such file", "cat missing.txt"),
            ok("Bash", command="pytest tests/a.py"),
        ]
        assert run(events * 3, repeat_threshold=10)["signals"] == []

    def test_edit_twice_then_failing_check_is_one_cycle(self) -> None:
        events = [ok("Edit", "a.py"), ok("Edit", "./a.py"), fail("Bash", "x", TEST_CMD)] * 3
        signals = run(events, repeat_threshold=10)["signals"]
        assert [(s["target"], s["count"]) for s in signals] == [("a.py", 3)]

    def test_changing_failure_is_progress(self) -> None:
        events = self.cycle("first") + self.cycle("second") + self.cycle("third")
        assert run(events)["stuck"] is False

    def test_passing_rerun_resets_the_state(self) -> None:
        events = self.cycle() * 2 + [ok("Edit", "src/a.py"), ok("Bash", command=TEST_CMD)]
        events += self.cycle()
        assert run(events, repeat_threshold=10)["stuck"] is False

    def test_several_edits_before_one_failure_count_once(self) -> None:
        events = [ok("Edit", "a.py"), ok("Edit", "a.py"), fail("Bash", "same", TEST_CMD)] * 2
        assert run(events, repeat_threshold=10)["stuck"] is False
        signals = run(events * 2, churn_threshold=4, repeat_threshold=10)["signals"]
        assert [(s["target"], s["count"]) for s in signals] == [("a.py", 4)]

    def test_target_spellings_are_normalized(self) -> None:
        events = []
        for target in ("./src/a.py", "src//a.py", "src\\a.py"):
            events += [ok("Edit", target), fail("Bash", "same", TEST_CMD)]
        signals = run(events, repeat_threshold=10)["signals"]
        assert [s["target"] for s in signals] == ["src/a.py"]

    def test_edit_without_target_is_not_an_edit(self) -> None:
        events = [ok("Edit"), fail("Bash", "boom", TEST_CMD)] * 3
        assert run(events, repeat_threshold=10)["stuck"] is False

    def test_failed_edits_below_threshold_are_not_stuck(self) -> None:
        bad_edit = {"tool": "Edit", "ok": False, "error": "old_string not found", "target": "a"}
        assert run([bad_edit, bad_edit, fail("Bash", "boom")])["stuck"] is False

    def test_failure_before_any_edit_is_not_an_outcome(self) -> None:
        assert run([fail("Bash", "boom"), ok("Edit", "a.py"), ok("Bash")])["signals"] == []

    def test_other_edit_tools_count(self) -> None:
        events = []
        for tool in ("Write", "MultiEdit", "apply_patch"):
            events += [ok(tool, "b.py"), fail("Bash", "same", TEST_CMD)]
        assert [s["target"] for s in run(events, repeat_threshold=10)["signals"]] == ["b.py"]

    def test_one_failure_after_two_files(self) -> None:
        events = [ok("Edit", "a.py"), ok("Edit", "b.py"), fail("Bash", "same", TEST_CMD)] * 3
        targets = [s["target"] for s in run(events, repeat_threshold=10)["signals"]]
        assert targets == ["a.py", "b.py"]

    def test_both_signals_can_fire(self) -> None:
        assert kinds(run(self.cycle() * 3)) == ["failure-repeat", "edit-churn"]


class TestParseEvents:
    @pytest.mark.parametrize(
        ("raw", "message"),
        [
            ({"tool": "Bash"}, "JSON array"),
            (["x"], "event 0 is not an object"),
            ([{"ok": True}], "'tool' must be a non-empty string"),
            ([{"tool": "  ", "ok": True}], "'tool' must be a non-empty string"),
            ([{"tool": "Bash", "ok": "no"}], "'ok' must be true or false"),
            ([{"tool": "Bash", "ok": False, "error": 3}], "'error' must be a string"),
            ([{"tool": "Bash", "ok": True, "error": 3}], "'error' must be a string"),
            ([{"tool": "Bash", "ok": True, "input": []}], "'input' must be a string"),
            ([{"tool": "Bash", "ok": True, "input": None}], "'input' must be a string"),
            ([{"tool": "Bash", "ok": True, "input": 5}], "'input' must be a string"),
            ([{"tool": "Edit", "ok": True, "input": None}], "'input' must be a string"),
            ([{"tool": "Bash", "ok": True, "check": "yes"}], "'check' must be true or false"),
            ([{"tool": "Bash", "ok": True, "check": None}], "'check' must be true or false"),
            ([{"tool": "Bash", "ok": True, "check": 0}], "'check' must be true or false"),
            ([{"tool": "Bash", "ok": True, "check": []}], "'check' must be true or false"),
            ([{"tool": "Edit", "ok": True, "target": 1}], "'target' must be a string"),
        ],
    )
    def test_rejects_bad_shapes(self, raw: Any, message: str) -> None:
        with pytest.raises(EventError, match=message):
            parse_events(raw)

    def test_rejects_too_many_events(self) -> None:
        with pytest.raises(EventError, match="limit"):
            parse_events([{"tool": "Bash", "ok": True}] * (mod.MAX_EVENTS + 1))

    def test_normalizes_and_ignores_unknown_keys(self) -> None:
        events = parse_events([{"tool": " Edit ", "ok": True, "target": "", "extra": 1}])
        assert events == [fc.FailureEvent(tool="edit", ok=True, error="", input=None, target=None)]
        assert events[0].edit_tool is True
        assert events[0].cycle_target is None

    def test_empty_list_is_not_stuck(self) -> None:
        assert check_failures(parse_events([])) == {
            "stuck": False,
            "events_total": 0,
            "events_checked": 0,
            "counts": {
                "tool_error": 0,
                "permission_denial": 0,
                "failed_retry": 0,
                "unfingerprinted": 0,
            },
            "signals": [],
            "untrusted": ["signals[].fingerprint", "signals[].target"],
        }


class TestCheckField:
    """AC-40 consumer A: the caller's `check` wins; absent means derive."""

    def test_absent_check_is_derived_from_the_command(self) -> None:
        [check, other] = parse_events([ok("Bash", command=TEST_CMD), ok("Bash", command="ls")])
        assert (check.check, check.is_check) == (None, True)
        assert (other.check, other.is_check) == (None, False)

    def test_json_string_command_is_derived(self) -> None:
        [event] = parse_events([ok("Bash", command='{"command":"pytest tests/a.py"}')])
        assert event.is_check is True

    def test_check_true_on_a_non_shell_tool_is_a_check(self) -> None:
        [event] = parse_events([{"tool": "Task", "ok": True, "check": True}])
        assert event.check is True and event.is_check is True

    def test_check_false_on_a_pytest_command_is_not_a_check(self) -> None:
        [event] = parse_events([{"tool": "Bash", "ok": True, "input": TEST_CMD, "check": False}])
        assert event.check is False and event.is_check is False

    def test_check_is_ignored_on_an_edit(self) -> None:
        [event] = parse_events([{"tool": "Edit", "ok": True, "target": "a.py", "check": True}])
        assert event.is_check is False
        assert event.cycle_target == "a.py"

    def test_check_false_success_leaves_the_cycle_open(self) -> None:
        # A different command, so the success's ProgressKey (AC-30) resets nothing here.
        marked = {"tool": "Bash", "ok": True, "input": "pytest tests/other.py", "check": False}
        events = [ok("Edit", "a.py"), marked, fail("Bash", "x", TEST_CMD)] * 3
        signals = run(events, repeat_threshold=10)["signals"]
        assert [(s["target"], s["count"]) for s in signals] == [("a.py", 3)]

    def test_check_true_failure_closes_the_cycle(self) -> None:
        marked = {"tool": "Task", "ok": False, "error": "verify failed", "check": True}
        events = [ok("Edit", "a.py"), marked] * 3
        signals = run(events, repeat_threshold=10)["signals"]
        assert [(s["target"], s["count"]) for s in signals] == [("a.py", 3)]


class TestAC39Canonicalization:
    @staticmethod
    def key(text: str) -> str:
        [event] = parse_events([fail("Bash", "boom", text)])
        assert event.input is not None
        return event.input

    def test_keys_out_of_order_and_whitespace_give_one_key(self) -> None:
        assert self.key('{"b": 1,   "a": 2}') == self.key(' {"a":2,\n"b":1} ') == '{"a":2,"b":1}'

    def test_non_ascii_is_escaped(self) -> None:
        assert self.key('{"a": "é"}') == '{"a":"\\u00e9"}'

    def test_repeated_key_last_wins(self) -> None:
        assert self.key('{"a": 1, "a": 2}') == '{"a":2}'

    @pytest.mark.parametrize("text", ["NaN", "Infinity", '{"a": NaN}'])
    def test_nan_text_is_plain_text(self, text: str) -> None:
        assert self.key(f"  {text} ") == text

    def test_non_json_command_is_trimmed_only(self) -> None:
        assert self.key("  pytest -k 'a b'  ") == "pytest -k 'a b'"

    def test_reordered_non_ascii_json_failures_are_retries(self) -> None:
        events = [
            fail("Bash", "boom", '{"b": "é", "a": 1}'),
            fail("Bash", "boom", '{"a":1,"b":"\\u00e9"}'),
        ]
        assert run(events)["counts"]["failed_retry"] == 1


class TestThresholdValidation:
    @pytest.mark.parametrize("name", ["repeat_threshold", "churn_threshold", "window"])
    def test_below_two_raises(self, name: str) -> None:
        with pytest.raises(ValueError, match=f"{name} \\(1\\) must be >= 2"):
            check_failures([], **{name: 1})
