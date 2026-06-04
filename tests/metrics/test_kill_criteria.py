"""Tests for the K1-K4 kill-criteria telemetry emitter (REQ-008-09).

Covers the canonical emitter (scripts/metrics/kill_criteria.py) and the
K3/K4 emission-point wrappers. The file-write boundary is mocked by
pointing the emitter at a tmp_path; subprocess boundaries in the K3 and K4
helpers are patched so no real pytest run or git access occurs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from scripts.metrics import kill_criteria


def _read_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# --- build_event ---------------------------------------------------------


def test_build_event_sets_schema_kind_and_detail() -> None:
    event = kill_criteria.build_event("K1", "axes/security.md")

    assert event["schemaVersion"] == kill_criteria.SCHEMA_VERSION
    assert event["kind"] == "K1"
    assert event["detail"] == "axes/security.md"
    assert isinstance(event["ts"], str) and event["ts"]


@pytest.mark.parametrize("kind", ["K1", "K2", "K3", "K4"])
def test_build_event_accepts_every_valid_kind(kind: str) -> None:
    event = kill_criteria.build_event(kind, "detail")

    assert event["kind"] == kind


def test_build_event_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown kill criterion"):
        kill_criteria.build_event(cast(kill_criteria.KillCriterion, "K9"), "detail")


# --- emit_event (write boundary mocked via tmp_path) ---------------------


def test_emit_event_appends_one_jsonl_line(tmp_path: Path) -> None:
    events_path = tmp_path / "drift-events.jsonl"

    kill_criteria.emit_event("K1", "first", events_path=events_path)

    events = _read_events(events_path)
    assert len(events) == 1
    assert events[0]["kind"] == "K1"
    assert events[0]["detail"] == "first"


def test_emit_event_is_append_only_across_calls(tmp_path: Path) -> None:
    events_path = tmp_path / "drift-events.jsonl"

    kill_criteria.emit_event("K1", "first", events_path=events_path)
    kill_criteria.emit_event("K2", "second", events_path=events_path)

    events = _read_events(events_path)
    assert [e["kind"] for e in events] == ["K1", "K2"]
    assert [e["detail"] for e in events] == ["first", "second"]


def test_emit_event_creates_parent_directory(tmp_path: Path) -> None:
    events_path = tmp_path / "nested" / "deeper" / "drift-events.jsonl"

    kill_criteria.emit_event("K3", "breakage", events_path=events_path)

    assert events_path.is_file()
    assert _read_events(events_path)[0]["kind"] == "K3"


def test_emit_event_returns_written_event(tmp_path: Path) -> None:
    events_path = tmp_path / "drift-events.jsonl"

    returned = kill_criteria.emit_event("K4", "mismatch", events_path=events_path)

    assert returned == _read_events(events_path)[0]


def test_append_line_flushes_before_unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class Handle:
        def __enter__(self):
            return self

        def __exit__(self, *_exc: object) -> None:
            events.append("close")

        def write(self, _line: str) -> None:
            events.append("write")

        def flush(self) -> None:
            events.append("flush")

    def lock_file(_handle: object) -> None:
        events.append("lock")

    def unlock_file(_handle: object) -> None:
        events.append("unlock")

    monkeypatch.setattr(kill_criteria, "_try_lock_helpers", lambda: (lock_file, unlock_file))
    monkeypatch.setattr(kill_criteria.Path, "open", lambda *_args, **_kwargs: Handle())

    kill_criteria._append_line(Path("drift-events.jsonl"), "x\n")

    assert events == ["lock", "write", "flush", "unlock", "close"]


def test_repo_root_is_anchored_to_module_not_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert kill_criteria._repo_root() == Path(kill_criteria.__file__).resolve().parents[2]


def test_emit_event_rejects_unknown_kind_before_writing(tmp_path: Path) -> None:
    events_path = tmp_path / "drift-events.jsonl"

    with pytest.raises(ValueError):
        kill_criteria.emit_event(
            cast(kill_criteria.KillCriterion, "BOGUS"),
            "x",
            events_path=events_path,
        )

    assert not events_path.exists()


# --- CLI -----------------------------------------------------------------


def test_cli_writes_event_and_returns_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    monkeypatch.setattr(kill_criteria, "_repo_root", lambda: tmp_path)
    events_path = "drift-events.jsonl"

    rc = kill_criteria.main(
        ["--kind", "K2", "--detail", "ci regression", "--events-path", events_path]
    )

    assert rc == 0
    events = _read_events(tmp_path / events_path)
    assert events[0]["kind"] == "K2"
    printed = json.loads(capsys.readouterr().out.strip())
    assert printed["detail"] == "ci regression"


def test_cli_returns_three_when_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(kill_criteria, "_append_line", boom)
    monkeypatch.setattr(kill_criteria, "_repo_root", lambda: tmp_path)

    rc = kill_criteria.main(
        ["--kind", "K1", "--detail", "x", "--events-path", "e.jsonl"]
    )

    assert rc == 3


@pytest.mark.parametrize(
    "raw",
    [
        "../drift-events.jsonl",
        "/outside/drift-events.jsonl",
        "C:\\outside\\drift-events.jsonl",
        "nested/\nfile.jsonl",
        ".",
        "nested/",
        "nested//file.jsonl",
        "drift-events.txt",
    ],
)
def test_cli_rejects_unsafe_events_path(raw: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(kill_criteria, "_repo_root", lambda: tmp_path)

    rc = kill_criteria.main(["--kind", "K1", "--detail", "x", "--events-path", raw])

    assert rc == 2
    assert not list(tmp_path.rglob("*.jsonl"))


def test_cli_rejects_invalid_kind_argument(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        kill_criteria.main(["--kind", "K9", "--detail", "x"])

    # argparse rejects an out-of-choices value with exit code 2.
    assert excinfo.value.code == 2
