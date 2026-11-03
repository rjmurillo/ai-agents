"""Tests for scripts/metrics/friction_fit.py (REQ-048 AC-19 reproducible fit)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.failure_classifier import FRICTION_WEIGHTS, FailureSignals, friction_score
from scripts.metrics import friction_fit as ff

# Counts are positional: tool_error, permission_denial, stop_feedback, error_streak.
QUIET = (0, 0, 0, 0)
LOUD = (0, 2, 3, 1)  # weights (0,2,2,1) score 4 + 6 + 1 = 11


def test_wilson_matches_known_values() -> None:
    low, high = ff.wilson_bounds(12, 16)
    assert round(low, 3) == 0.505
    assert round(high, 3) == 0.898
    assert round(ff.wilson_lower(15, 20), 3) == 0.531
    assert ff.wilson_bounds(0, 0) == (0.0, 0.0)
    assert ff.wilson_lower(0, 10) == pytest.approx(0.0, abs=1e-9)
    assert ff.wilson_bounds(10, 10)[1] == pytest.approx(1.0, abs=1e-9)


def test_signals_use_shipped_weight_names() -> None:
    assert set(ff.SIGNAL_NAMES) <= set(FRICTION_WEIGHTS)
    fields = {name: field for name, field, _ in ff.SIGNALS}
    assert fields == {
        "tool_error": "tool_error",
        "permission_denial": "denial_v2",
        "stop_feedback": "stop_feedback",
        "error_streak": "error_streak_max",
    }


def test_score_matches_shipped_friction_score() -> None:
    signals = FailureSignals(tool_error=3, permission_denial=2, error_streak=4)
    counts = (3, 2, 5, 4)
    shipped = friction_score(signals, stop_feedback=5)
    by_name = dict(zip(ff.SIGNAL_NAMES, counts, strict=True))
    shipped_weights = tuple(FRICTION_WEIGHTS[n] for n in ff.SIGNAL_NAMES)
    assert ff.weighted_sum(dict(FRICTION_WEIGHTS), by_name) == shipped
    assert ff.stop_score(shipped_weights, counts) == shipped


def test_weighted_sum_rejects_unknown_signal() -> None:
    with pytest.raises(KeyError):
        ff.weighted_sum({"bogus": 1}, {"tool_error": 1})


def test_firing_unit_is_first_stop_at_or_above_threshold() -> None:
    weights = (0, 2, 2, 1)
    stops = [(0, QUIET), (3, (0, 1, 1, 1)), (7, LOUD), (9, LOUD)]
    assert ff.stop_score(weights, (0, 1, 1, 1)) == 5
    assert ff.firing_unit(stops, weights, 5) == 3
    assert ff.firing_unit(stops, weights, 6) == 7
    assert ff.firing_unit(stops, weights, 11) == 7
    assert ff.firing_unit(stops, weights, 12) is None
    assert ff.firing_unit([], weights, 1) is None


def _pre() -> ff.Pre:
    return {"a": [(0, LOUD)], "b": [(0, QUIET), (2, (0, 1, 1, 1))], "c": [(0, QUIET)]}


def test_tally_counts_worth_and_unlabeled_units() -> None:
    labels = {("a", 0): "worth_it", ("b", 2): "not_worth_it"}
    assert ff.tally(_pre(), labels, ["a", "b", "c"], (0, 2, 2, 1), 5) == (2, 1, 0)
    assert ff.tally(_pre(), {("a", 0): "worth_it"}, ["a", "b", "c"], (0, 2, 2, 1), 5) == (2, 1, 1)


def test_unlabeled_firing_unit_makes_config_ineligible() -> None:
    labelled = {("a", 0): "worth_it", ("b", 2): "worth_it"}
    assert ff.best_config(_pre(), labelled, ["a", "b", "c"], 2) is not None
    partial = {("a", 0): "worth_it"}
    # A config firing on "b" has an unlabeled unit, so only configs firing on
    # "a" alone (n=1) remain, and min_units=2 rules those out.
    assert ff.best_config(_pre(), partial, ["a", "b", "c"], 2) is None
    assert ff.best_config(_pre(), partial, ["a", "b", "c"], 1) is not None


def test_best_config_tie_break_prefers_lower_weight_then_lower_threshold() -> None:
    pre: ff.Pre = {"a": [(0, (0, 0, 0, 8))]}
    best = ff.best_config(pre, {("a", 0): "worth_it"}, ["a"], 1)
    assert best is not None
    _, weights, threshold = best
    assert (weights, threshold) == ((0, 0, 0, 1), 6)


def test_folds_are_deterministic_and_partition_keys() -> None:
    keys = [f"s{i}" for i in range(23)]
    first = ff.make_folds(keys, 48002)
    assert first == ff.make_folds(keys, 48002)
    assert first != ff.make_folds(keys, 7)
    assert sorted(k for fold in first for k in fold) == sorted(keys)
    assert len(first) == ff.FOLDS


def test_load_labels_keeps_only_tune_rows(tmp_path: Path) -> None:
    path = tmp_path / "labels.csv"
    path.write_text(
        "split,session_id,stop,label\ntune,s1,2,worth_it\nheldout,s2,0,worth_it\n",
        encoding="utf-8",
    )
    assert ff.load_labels(path) == {("s1", 2): "worth_it"}


def test_load_labels_rejects_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "labels.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ff.InputError):
        ff.load_labels(path)


def _write_inputs(tmp_path: Path) -> list[str]:
    stop = {"index": 0, "tool_error": 0, "denial_v2": 2, "stop_feedback": 3, "error_streak_max": 1}
    rows = [{"session_id": f"s{i}", "stops": [stop]} for i in range(6)]
    (tmp_path / "sessions.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    (tmp_path / "split.json").write_text(
        json.dumps({"tune": [f"s{i}" for i in range(6)]}), encoding="utf-8"
    )
    lines = ["split,session_id,stop,label"] + [f"tune,s{i},0,worth_it" for i in range(6)]
    (tmp_path / "labels.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [
        "--sessions", str(tmp_path / "sessions.jsonl"),
        "--split", str(tmp_path / "split.json"),
        "--labels", str(tmp_path / "labels.csv"),
        "--min-train", "1",
        "--min-final", "1",
    ]  # fmt: skip


def test_cli_prints_folds_pooled_and_final(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert ff.main(_write_inputs(tmp_path)) == 0
    out = capsys.readouterr().out
    assert out.count("fold ") == ff.FOLDS
    assert "CV pooled 6/6" in out
    assert "wilson95_lb=" in out
    assert "final tool_error=" in out


@pytest.mark.parametrize("missing", ["sessions", "split", "labels"])
def test_cli_exits_2_on_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], missing: str
) -> None:
    argv = _write_inputs(tmp_path)
    (
        tmp_path
        / (
            missing
            + (".jsonl" if missing == "sessions" else ".csv" if missing == "labels" else ".json")
        )
    ).unlink()
    assert ff.main(argv) == 2
    assert "error:" in capsys.readouterr().err


def test_cli_exits_2_when_tuning_session_absent(tmp_path: Path) -> None:
    argv = _write_inputs(tmp_path)
    (tmp_path / "split.json").write_text(json.dumps({"tune": ["ghost"]}), encoding="utf-8")
    assert ff.main(argv) == 2
