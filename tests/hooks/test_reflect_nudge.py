"""Tests for the Stop-hook reflect nudge: parsing, scanning, run, main (issue #5817).

State, dedupe, and registered-path tests live in test_reflect_nudge_state.py.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.hooks.reflect_nudge_support import (
    human,
    nudge,
    payload,
    run_hook,
    scan,
    tool_result,
    write_transcript,
)


@pytest.fixture
def corrected(tmp_path: Path) -> Path:
    return write_transcript(
        tmp_path / "t.jsonl",
        [human("No, use the skill script"), human("fine"), human("that's wrong")],
    )


class TestReadPayload:
    def test_returns_object(self) -> None:
        assert nudge.read_payload(io.StringIO('{"session_id": "a"}')) == {"session_id": "a"}

    @pytest.mark.parametrize("raw", ["", "   ", "{not json", "[1, 2]", '"text"', "null"])
    def test_returns_none_for_bad_input(self, raw: str) -> None:
        assert nudge.read_payload(io.StringIO(raw)) is None

    def test_input_over_the_cap_is_rejected_not_truncated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(nudge, "MAX_STDIN_BYTES", 40)
        padded = '{"session_id": "a"}' + " " * 30
        assert nudge.read_payload(io.StringIO(padded)) is None
        assert nudge.read_payload(io.StringIO('{"session_id": "a"}')) is not None

    def test_cap_counts_utf8_bytes_not_characters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(nudge, "MAX_STDIN_BYTES", 20)
        multibyte = '{"s": "' + "\U0001f600" * 4 + '"}'  # 13 chars, 25 bytes
        assert len(multibyte) <= 20 < len(multibyte.encode("utf-8"))
        assert nudge.read_payload(io.StringIO(multibyte)) is None

    def test_returns_none_on_read_error(self) -> None:
        class Broken(io.StringIO):
            def read(self, size: int | None = -1) -> str:
                raise OSError("closed")

        assert nudge.read_payload(Broken()) is None


class TestIsHumanTurn:
    def test_typed_human_turn(self) -> None:
        assert nudge.is_human_turn(human("hello")) is True

    def test_queued_and_accepted_suggestion_are_human(self) -> None:
        assert nudge.is_human_turn(human("x", promptSource="queued")) is True
        assert nudge.is_human_turn(human("x", promptSource="suggestion_accepted")) is True

    def test_legacy_record_without_origin_uses_prompt_source(self) -> None:
        legacy = human("x")
        del legacy["origin"]
        assert nudge.is_human_turn(legacy) is True
        legacy["promptSource"] = "sdk"
        assert nudge.is_human_turn(legacy) is False

    def test_tool_result_is_not_human(self) -> None:
        assert nudge.is_human_turn(tool_result("no, wrong")) is False

    def test_tool_result_flag_beats_human_origin(self) -> None:
        assert nudge.is_human_turn(human("x", toolUseResult={})) is False

    @pytest.mark.parametrize(
        "extra",
        [
            {"isSidechain": True},
            {"isMeta": True},
            {"origin": {"kind": "task-notification"}},
            {"origin": {"kind": "peer"}},
            {"origin": "human"},
        ],
    )
    def test_non_human_shapes(self, extra: dict[str, Any]) -> None:
        assert nudge.is_human_turn(human("x", **extra)) is False

    def test_assistant_record_is_not_human(self) -> None:
        assert nudge.is_human_turn({"type": "assistant", "origin": {"kind": "human"}}) is False


class TestHumanText:
    def test_string_content(self) -> None:
        assert nudge.human_text(human("  hi")) == "hi"

    def test_text_blocks_join(self) -> None:
        rec = human("")
        rec["message"]["content"] = [{"type": "text", "text": "a"}, {"type": "image"}, "x"]
        assert nudge.human_text(rec) == "a"

    def test_harness_wrapper_is_empty(self) -> None:
        assert nudge.human_text(human("<command-name>/clear</command-name>")) == ""

    def test_bounded_length(self) -> None:
        assert len(nudge.human_text(human("a" * 5000))) == nudge.MAX_TURN_CHARS

    @pytest.mark.parametrize("message", [None, "text", {"content": 5}, {}])
    def test_unusable_message_is_empty(self, message: Any) -> None:
        rec = human("x")
        rec["message"] = message
        assert nudge.human_text(rec) == ""


class TestClassify:
    @pytest.mark.parametrize(
        "text",
        [
            "No, use the skill",
            "no.",
            "Nope",
            "no",
            "Wrong approach",
            "that's wrong",
            "That’s not right",
            "that is incorrect",
            "not like that",
            "not quite, see the issue",
            "try again",
            "ok, try again",
            "I meant the other file",
            "never do that",
            "don't ever amend",
            "stop doing that",
        ],
    )
    def test_corrections(self, text: str) -> None:
        assert nudge.classify(text)[0] is True

    @pytest.mark.parametrize(
        "text",
        [
            "now push it",
            "note the change",
            "nothing to add",
            "no need for extra API keys",
            "no problem",
            "I know",
            "notation matters",
            "wrongly typed field is fixed",
            "push",
            "the thing I said earlier works",
            "so I meant it",
            "",
        ],
    )
    def test_not_corrections(self, text: str) -> None:
        assert nudge.classify(text) == (False, False)

    @pytest.mark.parametrize(
        "text",
        ["Perfect", "exactly what I wanted", "great work", "that's it", "Yes, that's exactly"],
    )
    def test_praise(self, text: str) -> None:
        assert nudge.classify(text) == (False, True)


class TestScanTranscript:
    def test_counts_two_corrections(self, corrected: Path) -> None:
        result = scan(corrected)
        assert (result.human_turns, result.high, result.med) == (3, 2, 0)

    def test_ignores_correction_text_inside_tool_results(self, tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", [tool_result("No, wrong, incorrect")])
        result = scan(path)
        assert (result.user_records, result.human_turns, result.high) == (1, 0, 0)

    def test_negative_control_same_text_as_human_counts(self, tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", [human("No, wrong, incorrect")])
        assert scan(path).high == 1

    def test_malformed_lines_skipped_and_counted(self, tmp_path: Path) -> None:
        path = write_transcript(
            tmp_path / "t.jsonl", [human("no, wrong")], raw_lines=["{broken", "[1]", "", "   "]
        )
        result = scan(path)
        assert (result.high, result.skipped_lines) == (1, 2)

    def test_praise_counted_only_when_not_a_correction(self, tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", [human("perfect"), human("exactly")])
        result = scan(path)
        assert (result.high, result.med) == (0, 2)

    def test_stops_at_budget_and_reports_truncation(self, corrected: Path) -> None:
        ticks = iter([0.0, 0.0, 99.0, 99.0, 99.0])
        result = scan(corrected, clock=lambda: next(ticks), budget=1.0)
        assert result.truncated is True
        assert result.human_turns == 1

    def test_non_user_records_are_not_counted(self, tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", [{"type": "assistant", "message": "no"}])
        assert scan(path) == nudge.ScanResult()

    def test_over_long_line_is_skipped_and_scan_continues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(nudge, "MAX_LINE_CHARS", 400)
        path = tmp_path / "t.jsonl"
        long_line = json.dumps(human("no, " + "x" * 2000))
        path.write_text(
            long_line + "\n" + json.dumps(human("no, short")) + "\n", encoding="utf-8"
        )
        result = scan(path)
        assert (result.high, result.skipped_lines) == (1, 1)

    def test_over_long_final_line_without_newline_is_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(nudge, "MAX_LINE_CHARS", 64)
        path = tmp_path / "t.jsonl"
        path.write_text("y" * 300, encoding="utf-8")
        assert scan(path).skipped_lines == 1

    def test_deeply_nested_json_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        deep = "[" * 100_000 + "]" * 100_000
        path.write_text(deep + "\n" + json.dumps(human("no, x")) + "\n", encoding="utf-8")
        result = scan(path)
        assert (result.high, result.skipped_lines) == (1, 1)

    def test_invalid_utf8_is_replaced_not_fatal(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_bytes(b"\xff\xfe\n" + json.dumps(human("no, x")).encode() + b"\n")
        result = scan(path)
        assert (result.high, result.skipped_lines) == (1, 1)


class TestOpenTranscript:
    def test_opens_regular_file(self, corrected: Path) -> None:
        handle = nudge.open_transcript(str(corrected))
        assert handle is not None
        handle.close()

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert nudge.open_transcript(str(tmp_path / "gone.jsonl")) is None

    def test_directory_returns_none(self, tmp_path: Path) -> None:
        assert nudge.open_transcript(str(tmp_path)) is None

    def test_oversized_file_returns_none(
        self, corrected: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(nudge, "MAX_TRANSCRIPT_BYTES", 5)
        assert nudge.open_transcript(str(corrected)) is None

    @pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs mkfifo")
    def test_fifo_returns_none_without_blocking(self, tmp_path: Path) -> None:
        fifo = tmp_path / "pipe"
        os.mkfifo(fifo)
        assert nudge.open_transcript(str(fifo)) is None


class TestSignalRules:
    def test_threshold(self) -> None:
        assert nudge.has_signal(nudge.ScanResult(high=1)) is True
        assert nudge.has_signal(nudge.ScanResult(med=1)) is False
        assert nudge.has_signal(nudge.ScanResult(med=2)) is True
        assert nudge.has_signal(nudge.ScanResult()) is False

    def test_hash_changes_with_signal_set(self) -> None:
        a = nudge.signal_hash(nudge.ScanResult(high=1))
        assert a == nudge.signal_hash(nudge.ScanResult(high=1, human_turns=9))
        assert a != nudge.signal_hash(nudge.ScanResult(high=2))
        assert a != nudge.signal_hash(nudge.ScanResult(high=1, med=1))

    def test_default_state_root(self) -> None:
        assert nudge.default_state_root({"XDG_STATE_HOME": "/s"}, "posix") == Path("/s")
        assert nudge.default_state_root({}, "posix").parts[-2:] == (".local", "state")
        assert nudge.default_state_root({"LOCALAPPDATA": "/l"}, "nt") == Path("/l")
        relative = nudge.default_state_root({"XDG_STATE_HOME": "rel/state"}, "posix")
        assert relative.is_absolute()
        assert nudge.default_state_root({}, "nt").parts[-2:] == ("AppData", "Local")
        assert nudge.default_state_root({"LOCALAPPDATA": "rel"}, "nt").is_absolute()


class TestRun:
    def test_nudges_with_counts_and_no_block(self, corrected: Path, tmp_path: Path) -> None:
        code, out, err = run_hook(payload(corrected), tmp_path / "state")
        doc = json.loads(out)
        assert code == 0
        assert set(doc) == {"systemMessage"}
        assert "2 correction" in doc["systemMessage"] and "reflect" in doc["systemMessage"]
        assert "decision" not in out and "block" not in out
        assert "3 human turns, 2 HIGH" in err and "nudged" in err

    def test_message_never_quotes_transcript_text(self, corrected: Path, tmp_path: Path) -> None:
        _, out, err = run_hook(payload(corrected), tmp_path / "state")
        assert "skill script" not in out + err

    def test_silent_without_signal(self, tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", [human("push it"), human("continue")])
        code, out, err = run_hook(payload(path), tmp_path / "state")
        assert (code, out) == (0, "")
        assert "0 HIGH" in err and "silent" in err
        assert not (tmp_path / "state").exists()

    def test_missing_transcript_key_fails_open(self, tmp_path: Path) -> None:
        code, out, err = run_hook(payload(None), tmp_path / "state")
        assert (code, out) == (0, "")
        assert "fail-open" in err

    def test_negative_control_key_present_blocks_nothing_but_nudges(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        _, without, _ = run_hook(payload(None), tmp_path / "s1")
        _, with_key, _ = run_hook(payload(corrected), tmp_path / "s2")
        assert without == "" and "systemMessage" in with_key

    @pytest.mark.parametrize("raw", ["", "{bad", "[]"])
    def test_bad_payload_fails_open(self, raw: str, tmp_path: Path) -> None:
        code, out, err = run_hook(raw, tmp_path / "state")
        assert (code, out) == (0, "")
        assert "payload missing or malformed" in err

    @pytest.mark.parametrize("session_id", [None, 5, "", "../evil", "a/b", "a\n", "x" * 200])
    def test_invalid_session_id_fails_open(
        self, session_id: Any, corrected: Path, tmp_path: Path
    ) -> None:
        body = json.loads(payload(corrected))
        body["session_id"] = session_id
        code, out, err = run_hook(json.dumps(body), tmp_path / "state")
        assert (code, out) == (0, "")
        assert "session_id" in err

    def test_missing_transcript_file_fails_open(self, tmp_path: Path) -> None:
        code, out, err = run_hook(payload(tmp_path / "gone.jsonl"), tmp_path / "state")
        assert (code, out) == (0, "")
        assert "transcript_path" in err

    def test_directory_and_blank_path_fail_open(self, tmp_path: Path) -> None:
        for value in (str(tmp_path), "  ", 7):
            body = {"session_id": "s", "transcript_path": value}
            code, out, _ = run_hook(json.dumps(body), tmp_path / "state")
            assert (code, out) == (0, "")

    def test_oversized_transcript_fails_open(
        self, corrected: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(nudge, "MAX_TRANSCRIPT_BYTES", 5)
        code, out, err = run_hook(payload(corrected), tmp_path / "state")
        assert (code, out) == (0, "")
        assert "too large" in err

    def test_scan_timeout_still_reports_partial_counts(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        ticks = iter([0.0, 0.0, 99.0, 99.0, 99.0])
        code, out, err = run_hook(payload(corrected), tmp_path / "state", clock=lambda: next(ticks))
        assert code == 0
        assert "truncated" in err and "systemMessage" in out


class TestMain:
    def test_internal_error_exits_zero_with_warning(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def boom(*_a: Any, **_k: Any) -> int:
            raise RuntimeError("kaput")

        monkeypatch.setattr(nudge, "run", boom)
        assert nudge.main() == 0
        err = capsys.readouterr().err
        assert "[WARNING] reflect-trigger error: RuntimeError: kaput" in err

    def test_main_delegates_to_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(nudge, "run", lambda *_a, **_k: 0)
        assert nudge.main() == 0


