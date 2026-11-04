"""Codex converter safety tests: hostile ids, symlinks, deep nesting, and ~ paths.

Split from test_convert_codex.py to stay under the file-size lint.
"""

from __future__ import annotations

import json
import stat
from datetime import date
from pathlib import Path

import pytest

from scripts.metrics import convert_codex as cc
from tests.metrics.test_convert_codex import _cmd, _convert, _meta, _write_src


@pytest.mark.parametrize("hostile", ["../x", "a/b", "", ".hidden"])
def test_hostile_session_id_falls_back_to_the_safe_file_stem(tmp_path: Path, hostile: str) -> None:
    src = _write_src(tmp_path / "rollout-a.jsonl", _meta(id=hostile), _cmd("c", "x", 0, ""))
    out = tmp_path / "out"
    out.mkdir()
    totals = cc.convert_files([src], out, date(2026, 1, 1))
    assert totals["sessions"] == 1 and totals.get("skipped_unsafe_id", 0) == 0
    assert [p.name for p in out.iterdir()] == ["rollout-a.jsonl"]
    assert not (tmp_path / "x.jsonl").exists()


def test_unsafe_id_and_unsafe_stem_is_skipped(tmp_path: Path) -> None:
    src = _write_src(tmp_path / "rollout a.jsonl", _meta(id="../x"), _cmd("c", "x", 0, ""))
    out = tmp_path / "out"
    out.mkdir()
    totals = cc.convert_files([src], out, date(2026, 1, 1))
    assert (totals["sessions"], totals["skipped_unsafe_id"]) == (0, 1)
    assert list(out.iterdir()) == []


def test_planted_symlink_at_output_is_not_written_through(tmp_path: Path) -> None:
    src = _write_src(tmp_path / "rollout-a.jsonl", _meta(), _cmd("c", "x", 0, ""))
    out = tmp_path / "out"
    out.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_text("keep", encoding="utf-8")
    (out / "sess-1.jsonl").symlink_to(victim)
    cc.convert_files([src], out, date(2026, 1, 1))
    assert victim.read_text(encoding="utf-8") == "keep"
    target = out / "sess-1.jsonl"
    assert not target.is_symlink()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_missing_session_id_falls_back_to_the_file_stem(tmp_path: Path) -> None:
    from scripts.metrics import convert_codex as cc

    rollout = tmp_path / "rollout-2026-10-10T10-00-00-abc.jsonl"
    rollout.write_text(
        json.dumps(
            {
                "type": "event_msg",
                "timestamp": "2026-10-10T10:00:00Z",
                "payload": {"type": "user_message", "message": "fix the bug"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    out.mkdir()
    totals = cc.convert_files([str(rollout)], out, date(2026, 10, 1))
    assert totals.get("skipped_unsafe_id", 0) == 0
    assert (out / f"{rollout.stem}.jsonl").exists()


def test_deeply_nested_line_is_skipped_not_fatal() -> None:
    deep = "[" * 1_000_000 + "]" * 1_000_000
    _, _, recs = _convert(deep, _meta(), _cmd("c", "x", 1, "e"))
    assert recs


def test_deeply_nested_function_arguments_fall_back_to_raw_text() -> None:
    deep = "[" * 1_000_000 + "]" * 1_000_000
    assert cc._function_input(deep) == {"arguments": deep}


def test_main_expands_tilde_out_dir_before_guard_and_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    _write_src(tmp_path / "rollout-a.jsonl", _meta(), _cmd("c", "x", 1, "e"))
    code = cc.main(
        [
            "--src-glob",
            str(tmp_path / "rollout-*.jsonl"),
            "--out-dir",
            "~/out",
            "--since",
            "2026-10-01",
        ]
    )
    assert code == 0
    assert any((home / "out").glob("*.jsonl"))
    assert not (work / "~").exists()
