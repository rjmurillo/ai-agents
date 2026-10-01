"""In-process tests of the reflect Stop hook entrypoint (issue #5817).

These exist so coverage tooling sees ``main``; the runtime-contract cases in
``test_reflect_nudge.py`` prove the same paths through the registered command.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import runpy
from pathlib import Path

import pytest

from tests.hooks.reflect_nudge_support import HOOK, human, write_transcript

_spec = importlib.util.spec_from_file_location("invoke_reflect_nudge_main", HOOK)
assert _spec is not None and _spec.loader is not None
nudge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nudge)


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv(nudge.DISABLE_ENV, raising=False)


def _run(monkeypatch: pytest.MonkeyPatch, payload: object) -> int:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    return nudge.main()


def _corrections(tmp_path: Path) -> Path:
    return write_transcript(tmp_path / "t.jsonl", [human("no, use x"), human("wrong")])


def test_main_notifies_once_then_stays_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"session_id": "s1", "transcript_path": str(_corrections(tmp_path))}
    assert _run(monkeypatch, payload) == 0
    first = capsys.readouterr()
    assert set(json.loads(first.out)) == {"systemMessage"}
    assert "(notified)" in first.err
    assert _run(monkeypatch, payload) == 0
    second = capsys.readouterr()
    assert second.out == ""
    assert "(silent)" in second.err


def test_main_disabled_and_reentry_are_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"session_id": "s1", "transcript_path": str(_corrections(tmp_path))}
    monkeypatch.setenv(nudge.DISABLE_ENV, "1")
    assert _run(monkeypatch, payload) == 0
    monkeypatch.delenv(nudge.DISABLE_ENV)
    assert _run(monkeypatch, payload | {"stop_hook_active": True}) == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")


@pytest.mark.parametrize(
    "payload", ["", "garbage", "[]", {"session_id": "s"}, {"transcript_path": "/x"}]
)
def test_main_fails_open(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], payload: object
) -> None:
    assert _run(monkeypatch, payload) == 0
    assert capsys.readouterr().out == ""


def test_main_does_not_nudge_when_marker_cannot_be_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("XDG_STATE_HOME", str(blocker))
    payload = {"session_id": "s1", "transcript_path": str(_corrections(tmp_path))}
    assert _run(monkeypatch, payload) == 0
    assert capsys.readouterr().out == ""


def test_prune_tolerates_unreadable_directory(tmp_path: Path) -> None:
    nudge._prune(tmp_path / "absent")


def test_marker_path_refuses_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    monkeypatch.setenv("XDG_STATE_HOME", str(link))
    assert nudge._marker_path("s") is None
    assert nudge.claim_session("s") is False


def test_default_state_home_is_under_user_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_STATE_HOME")
    assert nudge._state_dir() == Path.home() / ".local" / "state" / "ai-agents" / "reflect-nudge"


def test_scan_skips_non_object_json_and_ignores_other_types(tmp_path: Path) -> None:
    path = write_transcript(
        tmp_path / "t.jsonl", [{"type": "assistant"}], extra_lines=["[1]", "", "3"]
    )
    counts = nudge.scan_transcript(path)
    assert (counts["skipped"], counts["user_records"], counts["human_turns"]) == (2, 0, 0)


def test_prune_tolerates_undeletable_entry(tmp_path: Path) -> None:
    stale = tmp_path / "old.json"
    stale.mkdir()
    old = 1.0
    os.utime(stale, (old, old))
    nudge._prune(tmp_path)
    assert stale.exists()


def test_wrapper_fails_open_on_unexpected_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Broken:
        def read(self) -> str:
            raise RuntimeError("boom")

    monkeypatch.setattr("sys.stdin", Broken())
    with pytest.raises(SystemExit) as exited:
        runpy.run_path(str(HOOK), run_name="__main__")
    assert exited.value.code == 0
    assert "[WARNING] reflect-trigger error: boom" in capsys.readouterr().err


def test_main_reports_schema_drift_when_no_record_names_a_human(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    record = {"type": "user", "message": {"content": "no"}}
    path = write_transcript(tmp_path / "t.jsonl", [record])
    assert _run(monkeypatch, {"session_id": "s1", "transcript_path": str(path)}) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "schema drift" in captured.err
