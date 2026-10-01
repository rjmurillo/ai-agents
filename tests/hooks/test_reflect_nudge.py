"""Tests for the Stop-hook reflect nudge (issue #5817, PRD #5820).

Record fixtures mirror the key shapes measured on real transcripts: a human
turn carries ``origin.kind == "human"`` and ``promptSource``; a tool result
carries ``toolUseResult`` and ``sourceToolAssistantUUID`` and is recorded with
``type == "user"``.

The two runtime-contract tests at the bottom run the command string registered
in ``.claude/settings.json`` through a shell, so a payload field the event does
not send cannot hide behind helper-level tests (the #3184 failure).
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = REPO_ROOT / "templates" / "hooks" / "Stop" / "invoke_reflect_nudge.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("invoke_reflect_nudge", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["invoke_reflect_nudge"] = module
    # Never write bytecode into templates/hooks: the template-tree corpus test
    # lists every file under that directory.
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


nudge = _load()


def human(text: str, **extra: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": "user",
        "isSidechain": False,
        "origin": {"kind": "human"},
        "promptSource": "typed",
        "message": {"role": "user", "content": text},
    }
    record.update(extra)
    return record


def tool_result(text: str) -> dict[str, Any]:
    return {
        "type": "user",
        "isSidechain": False,
        "sourceToolAssistantUUID": "u-1",
        "toolUseResult": {"stdout": text},
        "message": {"role": "user", "content": [{"type": "tool_result", "content": text}]},
    }


def write_transcript(path: Path, records: list[Any], raw_lines: list[str] | None = None) -> Path:
    lines = [json.dumps(r) for r in records] + (raw_lines or [])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def payload(transcript: Path | None, session_id: str = "sess-1") -> str:
    body: dict[str, Any] = {"session_id": session_id, "cwd": "/work"}
    if transcript is not None:
        body["transcript_path"] = str(transcript)
    return json.dumps(body)


def run_hook(stdin_text: str, state_root: Path, **kwargs: Any) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = nudge.run(io.StringIO(stdin_text), out, err, {}, state_root=state_root, **kwargs)
    return code, out.getvalue(), err.getvalue()


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
            "I said push",
            "never do that",
            "don't ever amend",
            "stop doing that",
        ],
    )
    def test_corrections(self, text: str) -> None:
        assert nudge.classify(text) == (True, False) or nudge.classify(text)[0] is True

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
        result = nudge.scan_transcript(corrected)
        assert (result.human_turns, result.high, result.med) == (3, 2, 0)

    def test_ignores_correction_text_inside_tool_results(self, tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", [tool_result("No, wrong, incorrect")])
        result = nudge.scan_transcript(path)
        assert (result.user_records, result.human_turns, result.high) == (1, 0, 0)

    def test_negative_control_same_text_as_human_counts(self, tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", [human("No, wrong, incorrect")])
        assert nudge.scan_transcript(path).high == 1

    def test_malformed_lines_skipped_and_counted(self, tmp_path: Path) -> None:
        path = write_transcript(
            tmp_path / "t.jsonl", [human("no, wrong")], raw_lines=["{broken", "[1]", "", "   "]
        )
        result = nudge.scan_transcript(path)
        assert (result.high, result.skipped_lines) == (1, 2)

    def test_praise_counted_only_when_not_a_correction(self, tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", [human("perfect"), human("exactly")])
        result = nudge.scan_transcript(path)
        assert (result.high, result.med) == (0, 2)

    def test_stops_at_budget_and_reports_truncation(self, corrected: Path) -> None:
        ticks = iter([0.0, 0.0, 99.0, 99.0, 99.0])
        result = nudge.scan_transcript(corrected, clock=lambda: next(ticks), budget=1.0)
        assert result.truncated is True
        assert result.human_turns == 1

    def test_non_user_records_are_not_counted(self, tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", [{"type": "assistant", "message": "no"}])
        assert nudge.scan_transcript(path) == nudge.ScanResult()

    def test_invalid_utf8_is_replaced_not_fatal(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_bytes(b"\xff\xfe\n" + json.dumps(human("no, x")).encode() + b"\n")
        result = nudge.scan_transcript(path)
        assert (result.high, result.skipped_lines) == (1, 1)


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
        assert nudge.default_state_root({}, "nt").parts[-2:] == ("AppData", "Local")


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

    @pytest.mark.parametrize("session_id", [None, 5, "", "../evil", "a/b", "x" * 200])
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


class TestDedupe:
    def test_second_stop_with_same_signals_is_silent(self, corrected: Path, tmp_path: Path) -> None:
        state = tmp_path / "state"
        _, first, _ = run_hook(payload(corrected), state)
        code, second, err = run_hook(payload(corrected), state)
        assert "systemMessage" in first
        assert (code, second) == (0, "")
        assert "already nudged" in err

    def test_new_correction_earns_a_new_nudge(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        path = write_transcript(tmp_path / "t.jsonl", [human("no, x")])
        run_hook(payload(path), state)
        write_transcript(path, [human("no, x"), human("wrong again")])
        _, out, _ = run_hook(payload(path), state)
        assert "2 correction" in out

    def test_sessions_do_not_share_markers(self, corrected: Path, tmp_path: Path) -> None:
        state = tmp_path / "state"
        run_hook(payload(corrected, "a"), state)
        _, out, _ = run_hook(payload(corrected, "b"), state)
        assert "systemMessage" in out

    def test_marker_has_counts_and_hash_only_with_owner_permissions(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        state = tmp_path / "state"
        run_hook(payload(corrected), state)
        directory = state / nudge.STATE_SUBDIR
        marker = directory / "sess-1.json"
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert set(data) == {"v", "signal_hash", "high", "med"}
        assert "skill script" not in marker.read_text(encoding="utf-8")
        assert sorted(p.name for p in directory.iterdir()) == ["sess-1.json"]
        if os.name == "posix":
            assert (directory.stat().st_mode & 0o777) == 0o700
            assert (marker.stat().st_mode & 0o777) == 0o600

    @pytest.mark.parametrize("content", ["{torn", "[]", '{"v": 9, "signal_hash": "x"}', '{"v": 1}'])
    def test_torn_marker_fails_open_to_no_nudge(
        self, content: str, corrected: Path, tmp_path: Path
    ) -> None:
        directory = tmp_path / "state" / nudge.STATE_SUBDIR
        directory.mkdir(parents=True, mode=0o700)
        (directory / "sess-1.json").write_text(content, encoding="utf-8")
        code, out, err = run_hook(payload(corrected), tmp_path / "state")
        assert (code, out) == (0, "")
        assert "marker unreadable or torn" in err

    def test_marker_path_that_is_a_directory_fails_open(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        (tmp_path / "state" / nudge.STATE_SUBDIR / "sess-1.json").mkdir(parents=True)
        code, out, _ = run_hook(payload(corrected), tmp_path / "state")
        assert (code, out) == (0, "")

    @pytest.mark.skipif(os.name != "posix", reason="symlink semantics")
    def test_symlinked_marker_directory_is_refused(self, corrected: Path, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (state / nudge.STATE_SUBDIR).symlink_to(elsewhere)
        code, out, err = run_hook(payload(corrected), state)
        assert (code, out) == (0, "")
        assert "marker directory unsafe" in err
        assert list(elsewhere.iterdir()) == []

    @pytest.mark.skipif(os.name != "posix", reason="uid semantics")
    def test_directory_owned_by_another_user_is_refused(
        self, corrected: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        other_uid = os.getuid() + 1
        monkeypatch.setattr(nudge.os, "getuid", lambda: other_uid)
        code, out, err = run_hook(payload(corrected), tmp_path / "state")
        assert (code, out) == (0, "")
        assert "unsafe" in err

    def test_failed_replace_leaves_no_temp_file(
        self, corrected: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_a: Any, **_k: Any) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(nudge.os, "replace", boom)
        with pytest.raises(OSError):
            run_hook(payload(corrected), tmp_path / "state")
        assert list((tmp_path / "state" / nudge.STATE_SUBDIR).iterdir()) == []

    def test_old_markers_are_pruned_and_fresh_ones_kept(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        directory = tmp_path / "state" / nudge.STATE_SUBDIR
        directory.mkdir(parents=True, mode=0o700)
        old, fresh = directory / "old.json", directory / "fresh.json"
        old.write_text("{}", encoding="utf-8")
        fresh.write_text("{}", encoding="utf-8")
        age = nudge.MARKER_MAX_AGE_SECONDS + 10
        os.utime(old, (1, 1))
        now = fresh.stat().st_mtime
        nudge.prune_markers(directory, now + age - nudge.MARKER_MAX_AGE_SECONDS)
        assert not old.exists() and fresh.exists()

    def test_prune_is_bounded_and_survives_vanished_entries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for i in range(4):
            (tmp_path / f"{i}.json").write_text("{}", encoding="utf-8")
        os.utime(tmp_path / "0.json", (1, 1))
        monkeypatch.setattr(nudge, "MARKER_PRUNE_LIMIT", 2)
        nudge.prune_markers(tmp_path, 10**12)
        assert len(list(tmp_path.iterdir())) == 2
        stuck = tmp_path / "stuck"
        stuck.mkdir()
        (stuck / "child").write_text("x", encoding="utf-8")
        os.utime(stuck, (1, 1))
        nudge.prune_markers(tmp_path, 10**12)
        assert stuck.exists()


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


class TestRegisteredPath:
    """Drive the command registered in .claude/settings.json, assert exit status."""

    @staticmethod
    def _command() -> str:
        settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        entries = settings["hooks"]["Stop"]
        assert len(entries) == 1 and len(entries[0]["hooks"]) == 1
        hook = entries[0]["hooks"][0]
        assert hook["type"] == "command" and hook["timeout"] <= 10
        return str(hook["command"])

    def _invoke(self, stdin_text: str, state: Path) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(REPO_ROOT), "XDG_STATE_HOME": str(state)}
        return subprocess.run(
            self._command(),
            shell=True,
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=30,
            check=False,
        )

    @pytest.mark.skipif(os.name != "posix", reason="registered command is a POSIX shell string")
    def test_registered_command_nudges_and_exits_zero(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        stop_dir = REPO_ROOT / ".claude" / "hooks" / "Stop"
        before = sorted(p.name for p in stop_dir.iterdir())
        done = self._invoke(payload(corrected), tmp_path / "state")
        assert done.returncode == 0, done.stderr
        assert json.loads(done.stdout)["systemMessage"].startswith("reflect-trigger:")
        assert sorted(p.name for p in stop_dir.iterdir()) == before

    @pytest.mark.skipif(os.name != "posix", reason="registered command is a POSIX shell string")
    def test_registered_command_fails_open_without_transcript_path(self, tmp_path: Path) -> None:
        done = self._invoke(payload(None), tmp_path / "state")
        assert done.returncode == 0
        assert done.stdout == ""
        assert "fail-open" in done.stderr

    def test_rendered_hook_matches_template(self) -> None:
        rendered = REPO_ROOT / ".claude" / "hooks" / "Stop" / "invoke_reflect_nudge.py"
        assert rendered.read_bytes() == HOOK_PATH.read_bytes()
