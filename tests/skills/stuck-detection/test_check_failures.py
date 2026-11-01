#!/usr/bin/env python3
"""Tests for the stateless check-failures detector in stuck_detection."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/stuck-detection/stuck_detection.py")
check_failures = mod.check_failures
parse_events = mod.parse_events
failure_fingerprint = mod.failure_fingerprint
EventError = mod.EventError
main = mod.main


def fail(tool: str, error: str) -> dict[str, Any]:
    return {"tool": tool, "ok": False, "error": error}


def ok(tool: str, target: str | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {"tool": tool, "ok": True}
    if target is not None:
        event["target"] = target
    return event


def run(events: list[dict[str, Any]], **kwargs: int) -> dict[str, Any]:
    result: dict[str, Any] = check_failures(parse_events(events), **kwargs)
    return result


class TestFailureFingerprint:
    def test_numbers_and_hashes_collapse(self) -> None:
        a = failure_fingerprint("Bash", "error at line 12 in commit abcdef1234\nmore")
        b = failure_fingerprint("bash", "Error at line 99 in commit 0123456789ab")
        assert a == b == "bash|error at line N in commit H"

    def test_uses_first_nonblank_line(self) -> None:
        assert failure_fingerprint("Bash", "\n\n  boom  \nsecond") == "bash|boom"

    def test_different_errors_differ(self) -> None:
        assert failure_fingerprint("Bash", "no such file") != failure_fingerprint(
            "Bash", "permission denied"
        )

    def test_empty_error_keeps_tool(self) -> None:
        assert failure_fingerprint("Bash", "") == "bash|"

    def test_caps_length(self) -> None:
        key = failure_fingerprint("Bash", "x" * 500)
        assert len(key) == len("bash|") + mod.FINGERPRINT_MAX_CHARS


class TestFailureRepeat:
    def test_three_identical_failures_trip(self) -> None:
        events = [fail("Bash", "pytest: command not found")] * 3
        result = run(events)
        assert result["stuck"] is True
        assert result["signals"] == [
            {
                "signal": "failure-repeat",
                "fingerprint": "bash|pytest: command not found",
                "count": 3,
            }
        ]
        assert "Failure loop detected" in result["nudge"]
        assert "Same failure 3 times" in result["nudge"]

    def test_two_failures_do_not_trip(self) -> None:
        result = run([fail("Bash", "boom")] * 2)
        assert result == {"stuck": False, "events_checked": 2, "signals": []}

    def test_distinct_failures_do_not_trip(self) -> None:
        events = [fail("Bash", "a broke"), fail("Bash", "b broke"), fail("Bash", "c broke")]
        assert run(events)["stuck"] is False

    def test_same_error_on_different_tools_does_not_combine(self) -> None:
        events = [fail("Bash", "boom"), fail("Read", "boom"), fail("Grep", "boom")]
        assert run(events)["stuck"] is False

    def test_successes_never_count(self) -> None:
        assert run([ok("Bash")] * 10)["stuck"] is False

    def test_window_drops_old_failures(self) -> None:
        events = [fail("Bash", "boom")] * 3 + [ok("Read")] * 20
        result = run(events)
        assert result["stuck"] is False
        assert result["events_checked"] == 20

    def test_custom_threshold(self) -> None:
        events = [fail("Bash", "boom")] * 3
        assert run(events, repeat_threshold=4)["stuck"] is False
        assert run(events + [fail("Bash", "boom")], repeat_threshold=4)["stuck"] is True

    def test_sorted_most_frequent_first(self) -> None:
        events = [fail("Bash", "b")] * 3 + [fail("Bash", "a")] * 4
        keys = [s["fingerprint"] for s in run(events)["signals"]]
        assert keys == ["bash|a", "bash|b"]


class TestEditChurn:
    def cycle(self, error: str = "test_x failed", target: str = "src/a.py") -> list[dict[str, Any]]:
        return [ok("Edit", target), ok("Read"), fail("Bash", error)]

    def test_three_edits_same_failure_trip(self) -> None:
        events = self.cycle("e1 failed") + self.cycle("e1 failed") + self.cycle("e1 failed")
        signals = run(events, repeat_threshold=10)["signals"]
        assert signals == [
            {
                "signal": "edit-churn",
                "target": "src/a.py",
                "fingerprint": "bash|eN failed",
                "count": 3,
            }
        ]

    def test_nudge_names_the_file(self) -> None:
        events = self.cycle() * 3
        nudge = run(events, repeat_threshold=10)["nudge"]
        assert "src/a.py edited 3 times, same failure after each" in nudge

    def test_changing_failure_is_progress(self) -> None:
        events = self.cycle("first") + self.cycle("second") + self.cycle("third")
        assert run(events)["stuck"] is False

    def test_passing_check_breaks_the_chain(self) -> None:
        events = self.cycle() + self.cycle() + [ok("Edit", "src/a.py"), ok("Bash")] + self.cycle()
        assert run(events, repeat_threshold=10)["stuck"] is False

    def test_read_success_does_not_break_the_chain(self) -> None:
        events = self.cycle() * 3
        assert any(s["signal"] == "edit-churn" for s in run(events)["signals"])

    def test_edit_without_target_is_not_an_edit(self) -> None:
        events = [ok("Edit"), fail("Bash", "boom")] * 3
        signals = run(events, repeat_threshold=10)["signals"]
        assert signals == []

    def test_failed_edits_are_ignored(self) -> None:
        events = [{"tool": "Edit", "ok": False, "error": "old_string not found", "target": "a"}]
        events = events * 2 + [fail("Bash", "boom")]
        assert run(events)["stuck"] is False

    def test_failure_before_any_edit_is_not_an_outcome(self) -> None:
        events = [fail("Bash", "boom"), ok("Edit", "a.py"), ok("Bash")]
        assert run(events)["signals"] == []

    def test_other_edit_tools_count(self) -> None:
        events = []
        for tool in ("Write", "MultiEdit", "apply_patch"):
            events += [ok(tool, "b.py"), fail("Bash", "same")]
        signals = run(events, repeat_threshold=10)["signals"]
        assert [s["target"] for s in signals] == ["b.py"]

    def test_one_failure_after_two_files(self) -> None:
        events = []
        for _ in range(3):
            events += [ok("Edit", "a.py"), ok("Edit", "b.py"), fail("Bash", "same")]
        targets = [s["target"] for s in run(events, repeat_threshold=10)["signals"]]
        assert targets == ["a.py", "b.py"]

    def test_both_signals_can_fire(self) -> None:
        signals = run(self.cycle() * 3)["signals"]
        assert [s["signal"] for s in signals] == ["failure-repeat", "edit-churn"]


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
            ([{"tool": "Edit", "ok": True, "target": 1}], "'target' must be a string"),
        ],
    )
    def test_rejects_bad_shapes(self, raw: Any, message: str) -> None:
        with pytest.raises(EventError, match=message):
            parse_events(raw)

    def test_rejects_too_many_events(self) -> None:
        with pytest.raises(EventError, match="limit"):
            parse_events([{"tool": "Bash", "ok": True}] * (mod.MAX_EVENTS + 1))

    def test_ignores_unknown_keys_and_empty_target(self) -> None:
        events = parse_events([{"tool": "Edit", "ok": True, "target": "", "extra": 1}])
        assert events == [{"tool": "Edit", "ok": True, "error": "", "target": None}]

    def test_empty_list_is_not_stuck(self) -> None:
        assert check_failures(parse_events([])) == {
            "stuck": False,
            "events_checked": 0,
            "signals": [],
        }


class TestThresholdValidation:
    @pytest.mark.parametrize("name", ["repeat_threshold", "churn_threshold", "window"])
    def test_below_two_raises(self, name: str) -> None:
        with pytest.raises(ValueError, match=f"{name} \\(1\\) must be >= 2"):
            check_failures([], **{name: 1})


class TestCli:
    def test_reads_stdin_and_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps([fail("Bash", "x")] * 3)))
        assert main(["check-failures"]) == 0
        assert json.loads(capsys.readouterr().out)["stuck"] is True

    def test_reads_events_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        path = tmp_path / "events.json"
        path.write_text(json.dumps([ok("Bash")]), encoding="utf-8")
        assert main(["check-failures", "--events", str(path)]) == 0
        assert json.loads(capsys.readouterr().out)["stuck"] is False

    def test_threshold_flags(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        path = tmp_path / "events.json"
        path.write_text(json.dumps([fail("Bash", "x")] * 2), encoding="utf-8")
        assert main(["check-failures", "--events", str(path), "--repeat", "2"]) == 0
        assert json.loads(capsys.readouterr().out)["stuck"] is True

    @pytest.mark.parametrize(
        ("content", "flags", "message"),
        [
            ("not json", [], "not valid JSON"),
            ("{}", [], "JSON array"),
            ("[]", ["--window", "1"], "window (1) must be >= 2"),
        ],
    )
    def test_bad_input_exits_two(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        content: str,
        flags: list[str],
        message: str,
    ) -> None:
        path = tmp_path / "events.json"
        path.write_text(content, encoding="utf-8")
        assert main(["check-failures", "--events", str(path), *flags]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert message in captured.err

    def test_missing_file_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["check-failures", "--events", str(tmp_path / "missing.json")]) == 2
        assert "stuck-detection:" in capsys.readouterr().err

    def test_deeply_nested_json_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "events.json"
        path.write_text("[" * 100_000, encoding="utf-8")
        assert main(["check-failures", "--events", str(path)]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "nested too deeply" in captured.err
