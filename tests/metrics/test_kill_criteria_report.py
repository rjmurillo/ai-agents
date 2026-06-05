"""Tests for the kill-criteria weekly rollup report (REQ-008-09).

Covers the read side of scripts/metrics/kill_criteria.py: the trailing-window
tally, the per-criterion status classification against the REQ-008-09
thresholds, the markdown rendering, and the ``report`` CLI subcommand. The
file-read boundary is mocked by pointing the reader at a tmp_path; the clock is
injected so the 30-day window is deterministic.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.metrics import kill_criteria

# Fixed reference instant so window math is deterministic across runs.
NOW = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)


def _event_line(kind: str, ts: str, detail: str = "x") -> str:
    return json.dumps(
        {"schemaVersion": 1, "ts": ts, "kind": kind, "detail": detail},
        separators=(",", ":"),
    )


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


# --- _classify -----------------------------------------------------------


def test_classify_returns_ok_when_count_below_threshold_minus_one() -> None:
    assert kill_criteria._classify(0, 3) == "ok"
    assert kill_criteria._classify(1, 3) == "ok"


def test_classify_returns_approaching_when_one_short_of_threshold() -> None:
    assert kill_criteria._classify(2, 3) == "approaching"


def test_classify_returns_fired_at_threshold() -> None:
    assert kill_criteria._classify(3, 3) == "fired"


def test_classify_returns_fired_above_threshold() -> None:
    assert kill_criteria._classify(5, 3) == "fired"


def test_classify_hard_fail_criterion_fires_on_first_event() -> None:
    # K3 has a threshold of 1: a single event is already a fired hard fail.
    assert kill_criteria._classify(1, 1) == "fired"
    assert kill_criteria._classify(0, 1) == "ok"


# --- _parse_event_line ---------------------------------------------------


def test_parse_event_line_returns_dict_for_valid_event() -> None:
    line = _event_line("K1", _iso(1))

    event = kill_criteria._parse_event_line(line)

    assert event is not None
    assert event["kind"] == "K1"


def test_parse_event_line_returns_none_for_blank_line() -> None:
    assert kill_criteria._parse_event_line("   ") is None


def test_parse_event_line_returns_none_for_malformed_json() -> None:
    assert kill_criteria._parse_event_line("not json {") is None


def test_parse_event_line_returns_none_for_non_object_json() -> None:
    assert kill_criteria._parse_event_line("[1, 2, 3]") is None


def test_parse_event_line_returns_none_for_unknown_kind() -> None:
    line = _event_line("K9", _iso(1))

    assert kill_criteria._parse_event_line(line) is None


# --- _event_in_window ----------------------------------------------------


def test_event_in_window_true_for_recent_event() -> None:
    cutoff = NOW - timedelta(days=kill_criteria.WINDOW_DAYS)
    event = {"ts": _iso(2)}

    assert kill_criteria._event_in_window(event, cutoff) is True


def test_event_in_window_false_for_old_event() -> None:
    cutoff = NOW - timedelta(days=kill_criteria.WINDOW_DAYS)
    event = {"ts": _iso(40)}

    assert kill_criteria._event_in_window(event, cutoff) is False


def test_event_in_window_false_for_missing_ts() -> None:
    cutoff = NOW - timedelta(days=kill_criteria.WINDOW_DAYS)

    assert kill_criteria._event_in_window({}, cutoff) is False


def test_event_in_window_false_for_unparseable_ts() -> None:
    cutoff = NOW - timedelta(days=kill_criteria.WINDOW_DAYS)
    event = {"ts": "yesterday"}

    assert kill_criteria._event_in_window(event, cutoff) is False


def test_event_in_window_treats_naive_ts_as_utc() -> None:
    cutoff = NOW - timedelta(days=kill_criteria.WINDOW_DAYS)
    naive_recent = (NOW - timedelta(days=1)).replace(tzinfo=None).isoformat()

    assert kill_criteria._event_in_window({"ts": naive_recent}, cutoff) is True


# --- count_events_in_window ----------------------------------------------


def test_count_events_returns_zero_for_every_kind_when_empty() -> None:
    counts = kill_criteria.count_events_in_window([], NOW)

    assert counts == {"K1": 0, "K2": 0, "K3": 0, "K4": 0}


def test_count_events_tallies_each_kind_within_window() -> None:
    lines = [
        _event_line("K1", _iso(1)),
        _event_line("K1", _iso(2)),
        _event_line("K2", _iso(3)),
    ]

    counts = kill_criteria.count_events_in_window(lines, NOW)

    assert counts == {"K1": 2, "K2": 1, "K3": 0, "K4": 0}


def test_count_events_excludes_events_older_than_window() -> None:
    lines = [
        _event_line("K1", _iso(2)),
        _event_line("K1", _iso(40)),
    ]

    counts = kill_criteria.count_events_in_window(lines, NOW)

    assert counts["K1"] == 1


def test_count_events_skips_malformed_and_blank_lines() -> None:
    lines = [
        _event_line("K1", _iso(1)),
        "garbage",
        "",
        _event_line("K9", _iso(1)),
    ]

    counts = kill_criteria.count_events_in_window(lines, NOW)

    assert counts["K1"] == 1


def test_count_events_respects_event_exactly_at_window_boundary() -> None:
    # An event exactly window_days old sits at the cutoff and counts.
    lines = [_event_line("K4", _iso(kill_criteria.WINDOW_DAYS))]

    counts = kill_criteria.count_events_in_window(lines, NOW)

    assert counts["K4"] == 1


# --- build_rollups -------------------------------------------------------


def test_build_rollups_orders_kinds_and_attaches_thresholds() -> None:
    rollups = kill_criteria.build_rollups({"K1": 2, "K2": 0, "K3": 0, "K4": 0})

    assert [r.kind for r in rollups] == ["K1", "K2", "K3", "K4"]
    assert rollups[0].threshold == 3
    assert rollups[2].threshold == 1


def test_build_rollups_sets_fired_status_when_threshold_met() -> None:
    rollups = kill_criteria.build_rollups({"K1": 3, "K2": 0, "K3": 0, "K4": 0})

    k1 = next(r for r in rollups if r.kind == "K1")
    assert k1.status == "fired"


def test_build_rollups_defaults_missing_kind_to_zero() -> None:
    rollups = kill_criteria.build_rollups({"K1": 1})

    k4 = next(r for r in rollups if r.kind == "K4")
    assert k4.count == 0
    assert k4.status == "ok"


# --- render_report -------------------------------------------------------


def test_render_report_all_clear_headline_when_no_fired_or_approaching() -> None:
    rollups = kill_criteria.build_rollups({"K1": 0, "K2": 0, "K3": 0, "K4": 0})

    markdown = kill_criteria.render_report(rollups, NOW)

    assert "All clear" in markdown
    assert "2026-06-05" in markdown


def test_render_report_warns_when_a_criterion_is_approaching() -> None:
    rollups = kill_criteria.build_rollups({"K1": 2, "K2": 0, "K3": 0, "K4": 0})

    markdown = kill_criteria.render_report(rollups, NOW)

    assert "WARNING" in markdown
    assert "K1" in markdown


def test_render_report_alerts_when_a_criterion_fired() -> None:
    rollups = kill_criteria.build_rollups({"K1": 0, "K2": 0, "K3": 1, "K4": 0})

    markdown = kill_criteria.render_report(rollups, NOW)

    assert "ALERT" in markdown
    assert "K3" in markdown
    assert "FIRED" in markdown


def test_render_report_includes_a_table_row_for_every_kind() -> None:
    rollups = kill_criteria.build_rollups({"K1": 0, "K2": 0, "K3": 0, "K4": 0})

    markdown = kill_criteria.render_report(rollups, NOW)

    for kind in ("K1", "K2", "K3", "K4"):
        assert f"| {kind} |" in markdown


# --- report_events (read boundary mocked via tmp_path) -------------------


def test_report_events_returns_no_fired_for_empty_file(tmp_path: Path) -> None:
    events_path = tmp_path / "drift-events.jsonl"
    events_path.write_text("", encoding="utf-8")

    markdown, any_fired = kill_criteria.report_events(events_path=events_path, now=NOW)

    assert any_fired is False
    assert "All clear" in markdown


def test_report_events_handles_missing_file_as_no_events(tmp_path: Path) -> None:
    events_path = tmp_path / "does-not-exist.jsonl"

    markdown, any_fired = kill_criteria.report_events(events_path=events_path, now=NOW)

    assert any_fired is False
    assert "| K1 | drift hook false positives | 0 |" in markdown


def test_report_events_flags_fired_when_threshold_reached(tmp_path: Path) -> None:
    events_path = tmp_path / "drift-events.jsonl"
    events_path.write_text(
        "\n".join(
            [
                _event_line("K1", _iso(1)),
                _event_line("K1", _iso(2)),
                _event_line("K1", _iso(3)),
            ]
        ),
        encoding="utf-8",
    )

    markdown, any_fired = kill_criteria.report_events(events_path=events_path, now=NOW)

    assert any_fired is True
    assert "ALERT" in markdown


def test_report_events_uses_default_now_when_omitted(tmp_path: Path) -> None:
    events_path = tmp_path / "drift-events.jsonl"
    events_path.write_text("", encoding="utf-8")

    markdown, any_fired = kill_criteria.report_events(events_path=events_path)

    assert any_fired is False
    assert "Kill-Criteria Drift Telemetry" in markdown


# --- CLI: report subcommand ----------------------------------------------


def test_cli_report_returns_zero_when_nothing_fired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(kill_criteria, "_repo_root", lambda: tmp_path)
    (tmp_path / "drift-events.jsonl").write_text("", encoding="utf-8")

    rc = kill_criteria.main(["report", "--events-path", "drift-events.jsonl"])

    assert rc == 0
    assert "All clear" in capsys.readouterr().out


def test_cli_report_returns_one_when_a_criterion_fired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(kill_criteria, "_repo_root", lambda: tmp_path)
    # K3 fires on the first event.
    (tmp_path / "drift-events.jsonl").write_text(
        _event_line("K3", datetime.now(tz=UTC).isoformat()) + "\n",
        encoding="utf-8",
    )

    rc = kill_criteria.main(["report", "--events-path", "drift-events.jsonl"])

    assert rc == 1
    assert "ALERT" in capsys.readouterr().out


def test_cli_report_reads_repo_default_path_when_no_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(kill_criteria, "_repo_root", lambda: tmp_path)
    # No file at the default path: report still succeeds with zero counts.

    rc = kill_criteria.main(["report"])

    assert rc == 0
    assert "All clear" in capsys.readouterr().out


def test_cli_report_returns_three_when_read_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> tuple[str, bool]:
        raise OSError("permission denied")

    monkeypatch.setattr(kill_criteria, "report_events", boom)

    rc = kill_criteria.main(["report"])

    assert rc == 3


def test_cli_report_rejects_unsafe_events_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kill_criteria, "_repo_root", lambda: tmp_path)

    rc = kill_criteria.main(["report", "--events-path", "../escape.jsonl"])

    assert rc == 2


# --- CLI: emit still requires kind and detail ----------------------------


def test_cli_emit_returns_two_when_kind_missing(capsys) -> None:
    rc = kill_criteria.main(["--detail", "only detail"])

    assert rc == 2
    assert "requires --kind and --detail" in capsys.readouterr().err


def test_cli_emit_returns_two_when_detail_missing(capsys) -> None:
    rc = kill_criteria.main(["--kind", "K1"])

    assert rc == 2
    assert "requires --kind and --detail" in capsys.readouterr().err
