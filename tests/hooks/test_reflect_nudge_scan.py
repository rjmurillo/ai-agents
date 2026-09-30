"""Scanner and marker unit tests for the reflect Stop hook (issue #5817)."""

from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path

import pytest

from tests.hooks.reflect_nudge_support import HOOK, human, tool_result, write_transcript

_spec = importlib.util.spec_from_file_location("invoke_reflect_nudge", HOOK)
assert _spec is not None and _spec.loader is not None
nudge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nudge)


@pytest.mark.parametrize(
    "text",
    [
        "No",
        "no, use the other one",
        "Wrong.",
        "that's wrong",
        "That is incorrect",
        "not like that",
        "Not quite, see the issue",
        "I meant the other file",
        "never use raw gh",
        "don't ever do that",
        "stop adding comments",
    ],
)
def test_correction_phrases_match(text: str) -> None:
    assert nudge._CORRECTION.match(text.lower())


@pytest.mark.parametrize(
    "text",
    [
        "now add a test",
        "note the following",
        "nothing changed",
        "nobody knows",
        "notice this",
        "wronged",
    ],
)
def test_substrings_do_not_match_as_corrections(text: str) -> None:
    assert not nudge._CORRECTION.match(text.lower())


@pytest.mark.parametrize("text", ["perfect", "Perfect, thanks", "exactly!", "that's it", "great"])
def test_praise_phrases_match(text: str) -> None:
    assert nudge._PRAISE.match(text.lower())


def test_turn_text_rejects_non_human_shapes() -> None:
    assert nudge._turn_text(tool_result("no")) is None
    assert nudge._turn_text({"type": "assistant", "message": {"content": "no"}}) is None
    assert nudge._turn_text(human("no") | {"isSidechain": True}) is None
    assert nudge._turn_text(human("no") | {"isMeta": True}) is None
    assert nudge._turn_text(human("<command-name>/x</command-name>")) is None
    assert nudge._turn_text(human("no") | {"origin": {"kind": "peer"}}) is None
    assert nudge._turn_text(human("no") | {"origin": None}) is None
    assert nudge._turn_text({"type": "user", "message": {"content": "no"}}) is None


def test_turn_text_reads_text_blocks() -> None:
    record = human("x") | {"message": {"content": [{"type": "text", "text": " No "}, "junk"]}}
    assert nudge._turn_text(record) == "No"
    assert nudge._turn_text(human("x") | {"message": {"content": 5}}) is None
    assert nudge._turn_text(human("x") | {"message": None}) is None


def test_only_turn_head_is_scanned(tmp_path: Path) -> None:
    pasted = "here is a file: " + "x" * 300 + " no, wrong"
    path = write_transcript(tmp_path / "t.jsonl", [human(pasted)])
    assert nudge.scan_transcript(path)["high"] == 0


def test_scan_counts_scope(tmp_path: Path) -> None:
    records = [human("no"), human("perfect"), human("hello"), tool_result("no")]
    counts = nudge.scan_transcript(write_transcript(tmp_path / "t.jsonl", records, ["", "{x"]))
    assert counts == {"user_records": 4, "human_turns": 3, "high": 1, "med": 1, "skipped": 1}


@pytest.mark.parametrize(
    ("high", "med", "expected"),
    [(0, 0, False), (0, 1, False), (0, 2, True), (1, 0, True)],
)
def test_qualifies_threshold(high: int, med: int, expected: bool) -> None:
    assert nudge.qualifies({"high": high, "med": med}) is expected


def test_signal_hash_changes_with_counts() -> None:
    assert nudge.signal_hash({"high": 1, "med": 0}) != nudge.signal_hash({"high": 2, "med": 0})


def test_write_marker_failure_returns_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("XDG_STATE_HOME", str(blocker))
    assert nudge.write_marker("s", "h") is False


def test_stale_markers_are_pruned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert nudge.write_marker("old", "h")
    old = nudge._state_dir() / "old.json"
    stale = time.time() - nudge.MARKER_MAX_AGE_SECONDS - 60
    os.utime(old, (stale, stale))
    assert nudge.write_marker("new", "h")
    assert not old.exists()
    assert (nudge._state_dir() / "new.json").exists()


def test_already_nudged_states(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert nudge.already_nudged("s", "h") is False
    nudge.write_marker("s", "h")
    assert nudge.already_nudged("s", "h") is True
    assert nudge.already_nudged("s", "other") is False
