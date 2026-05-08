"""Tests for build/scripts/aggregate_guard_intercepts.py.

Synthetic event-log fixtures only; no live telemetry. Covers:

- Directory and file source modes
- STDIN mode via the script's argparse path
- Malformed lines silently skipped
- ``--guard`` injection of zero-event guards
- Time math for ``days_since_*`` fields with ``--now`` override
- Block / fail-open separation in counts and rates

Negative tests cover unreadable sources, bad JSON, and bad ``--now``.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import aggregate_guard_intercepts as agi  # noqa: E402

_FIXED_NOW = "2026-05-05T00:00:00+00:00"


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )


def _block(guard: str, ts: str) -> dict:
    return {
        "guard": guard,
        "code": f"E_{guard.upper().replace('-', '_')}",
        "outcome": "block",
        "violations": 1,
        "matched_files": 1,
        "changed_files": 3,
        "timestamp": ts,
    }


def _fail_open(guard: str, ts: str) -> dict:
    return {
        "guard": guard,
        "code": f"E_{guard.upper().replace('-', '_')}",
        "outcome": "fail_open",
        "reason": "exception",
        "detail": "boom",
        "timestamp": ts,
    }


# ---------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------

def test_aggregates_blocks_and_fail_opens_per_guard(tmp_path, capsys):
    log = tmp_path / "events.jsonl"
    _write_jsonl(log, [
        _block("markdown-lint", "2026-04-25T10:00:00+00:00"),
        _fail_open("markdown-lint", "2026-05-01T10:00:00+00:00"),
        _block("manifest-count", "2026-05-04T10:00:00+00:00"),
    ])
    rc = agi.main(["--source", str(log), "--now", _FIXED_NOW])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    out = json.loads(captured.out)
    assert set(out.keys()) == {"markdown-lint", "manifest-count"}
    md = out["markdown-lint"]
    assert md["total_events"] == 2
    assert md["blocks"] == 1
    assert md["fail_opens"] == 1
    assert md["block_rate"] == 0.5
    assert md["fail_open_rate"] == 0.5
    mc = out["manifest-count"]
    assert mc["total_events"] == 1
    assert mc["blocks"] == 1
    assert mc["fail_opens"] == 0
    assert mc["block_rate"] == 1.0


def test_directory_source_picks_up_all_jsonl(tmp_path, capsys):
    (tmp_path / "wk-a.jsonl").write_text(
        json.dumps(_block("g1", "2026-05-01T00:00:00+00:00")) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "wk-b.jsonl").write_text(
        json.dumps(_fail_open("g1", "2026-05-04T00:00:00+00:00")) + "\n",
        encoding="utf-8",
    )
    rc = agi.main(["--source", str(tmp_path), "--now", _FIXED_NOW])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    out = json.loads(captured.out)
    g = out["g1"]
    assert g["blocks"] == 1
    assert g["fail_opens"] == 1
    assert g["days_since_first_event"] > g["days_since_last_event"]


def test_event_prefix_is_stripped(tmp_path, capsys):
    log = tmp_path / "raw.jsonl"
    log.write_text(
        f"EVENT={json.dumps(_block('g1', '2026-05-01T00:00:00+00:00'))}\n",
        encoding="utf-8",
    )
    rc = agi.main(["--source", str(log), "--now", _FIXED_NOW])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["g1"]["blocks"] == 1


def test_explicit_guard_listed_with_zero_events(tmp_path, capsys):
    log = tmp_path / "events.jsonl"
    _write_jsonl(log, [_block("seen", "2026-05-01T00:00:00+00:00")])
    rc = agi.main(["--source", str(log), "--guard", "unseen", "--now", _FIXED_NOW])
    captured = capsys.readouterr()
    assert rc == 0
    out = json.loads(captured.out)
    assert "unseen" in out
    assert out["unseen"]["total_events"] == 0
    assert out["unseen"]["days_since_first_event"] is None


def test_stdin_mode_reads_event_lines(monkeypatch, capsys):
    payload = (
        "stderr noise\n"
        f"EVENT={json.dumps(_block('g1', '2026-05-01T00:00:00+00:00'))}\n"
        "more noise\n"
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    # io.StringIO has no isatty; force False via patch.
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    rc = agi.main(["--stdin", "--now", _FIXED_NOW])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["g1"]["blocks"] == 1


def test_age_computation_uses_now_override(tmp_path, capsys):
    log = tmp_path / "events.jsonl"
    _write_jsonl(log, [_block("g1", "2026-05-01T00:00:00+00:00")])
    rc = agi.main(["--source", str(log), "--now", "2026-05-08T00:00:00+00:00"])
    captured = capsys.readouterr()
    assert rc == 0
    g = json.loads(captured.out)["g1"]
    assert g["days_since_first_event"] == pytest.approx(7.0, abs=1e-6)


# ---------------------------------------------------------------------
# Lenience: malformed input
# ---------------------------------------------------------------------

def test_malformed_lines_are_skipped(tmp_path, capsys):
    log = tmp_path / "events.jsonl"
    log.write_text(
        "\n".join([
            "not json at all",
            "{not: valid}",
            "[]",  # not a dict
            "{}",  # missing required keys
            json.dumps({"guard": "g1"}),  # missing outcome
            json.dumps(_block("g1", "2026-05-01T00:00:00+00:00")),
        ]) + "\n",
        encoding="utf-8",
    )
    rc = agi.main(["--source", str(log), "--now", _FIXED_NOW])
    captured = capsys.readouterr()
    assert rc == 0
    out = json.loads(captured.out)
    assert out["g1"]["total_events"] == 1


# ---------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------

def test_no_events_and_no_guard_returns_logic_error(tmp_path, capsys):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    rc = agi.main(["--source", str(empty), "--now", _FIXED_NOW])
    captured = capsys.readouterr()
    assert rc == 1
    assert "nothing to summarize" in captured.err


def test_bad_now_returns_config_error(tmp_path, capsys):
    log = tmp_path / "events.jsonl"
    _write_jsonl(log, [_block("g1", "2026-05-01T00:00:00+00:00")])
    rc = agi.main(["--source", str(log), "--now", "not-a-date"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "invalid --now" in captured.err


def test_missing_source_returns_config_error(tmp_path, capsys):
    """An explicit ``--source`` pointing at a non-existent path is a caller
    config error (exit 2 per ADR-035), not a "no events to aggregate" data
    case (exit 1). The caller's exit-code handling depends on this split:
    config errors require fixing the invocation; logic errors are normal
    no-data flow that may be expected when guards are inert.
    """
    missing = tmp_path / "does-not-exist"
    rc = agi.main(["--source", str(missing), "--now", _FIXED_NOW])
    captured = capsys.readouterr()
    assert rc == 2
    assert "--source path does not exist" in captured.err


def test_event_without_guard_is_skipped(tmp_path, capsys):
    log = tmp_path / "events.jsonl"
    log.write_text(
        json.dumps({"guard": "", "outcome": "block"}) + "\n"
        + json.dumps(_block("g1", "2026-05-01T00:00:00+00:00")) + "\n",
        encoding="utf-8",
    )
    rc = agi.main(["--source", str(log), "--now", _FIXED_NOW])
    captured = capsys.readouterr()
    assert rc == 0
    out = json.loads(captured.out)
    assert "g1" in out and "" not in out
