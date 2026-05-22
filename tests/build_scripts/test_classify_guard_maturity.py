"""Tests for build/scripts/classify_guard_maturity.py.

Pin every Hook Maturity Model tier transition. Each test exercises a
single tier; together they cover all six (Budding, Growing, Mature,
Proficient, Inert, Harmful) plus the order-sensitive "Harmful wins
over everything" precedence rule.

Negative tests cover bad input shapes, unreadable files, and the CLI
parsing of stdin.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import classify_guard_maturity as cgm  # noqa: E402


def _summary(
    *,
    blocks: int = 0,
    fail_opens: int = 0,
    age: float | None = None,
    last_age: float | None = None,
) -> dict:
    total = blocks + fail_opens
    return {
        "guard": "test-guard",
        "total_events": total,
        "blocks": blocks,
        "fail_opens": fail_opens,
        "block_rate": (blocks / total) if total else 0.0,
        "fail_open_rate": (fail_opens / total) if total else 0.0,
        "first_event": None,
        "last_event": None,
        "days_since_first_event": age,
        "days_since_last_event": last_age if last_age is not None else age,
    }


# ---------------------------------------------------------------------
# Single-guard tier tests (all six tiers)
# ---------------------------------------------------------------------

def test_budding_under_14_days_any_intercepts():
    s = _summary(blocks=2, age=5.0)
    assert cgm.classify_one(s) == "Budding"


def test_budding_when_age_is_null_default_unseen():
    s = _summary(blocks=0, age=None)
    assert cgm.classify_one(s) == "Budding"


def test_growing_14_to_30_days_with_intercepts():
    s = _summary(blocks=1, age=20.0)
    assert cgm.classify_one(s) == "Growing"


def test_growing_lower_bound_at_14_days():
    s = _summary(blocks=1, age=14.0)
    assert cgm.classify_one(s) == "Growing"


def test_mature_30_plus_days_5_plus_intercepts_neutral_fitness():
    # Block rate exactly 0.5 -> fitness exactly 0.0, which qualifies for
    # Mature (fitness >= 0).
    s = _summary(blocks=3, fail_opens=3, age=45.0)
    assert cgm.classify_one(s) == "Mature"


def test_proficient_60_plus_days_10_plus_intercepts_positive_fitness():
    # 10 blocks, 0 fail_opens -> block_rate 1.0 -> fitness 0.5.
    s = _summary(blocks=10, age=90.0)
    assert cgm.classify_one(s) == "Proficient"


def test_inert_30_plus_days_zero_intercepts():
    s = _summary(blocks=0, fail_opens=0, age=45.0)
    assert cgm.classify_one(s) == "Inert"


def test_harmful_negative_fitness_at_any_age():
    # All fail-opens -> block_rate 0.0 -> fitness -0.5.
    s = _summary(fail_opens=3, age=2.0)
    assert cgm.classify_one(s) == "Harmful"


def test_harmful_precedence_beats_proficient():
    # 60 days, 10 intercepts, but all are fail-opens -> Harmful first.
    s = _summary(fail_opens=10, age=90.0)
    assert cgm.classify_one(s) == "Harmful"


def test_treat_unseen_as_inert_flips_null_age_to_inert():
    s = _summary(blocks=0, age=None)
    assert cgm.classify_one(s, treat_unseen_as_inert=True) == "Inert"


# ---------------------------------------------------------------------
# Edge transitions and boundary semantics
# ---------------------------------------------------------------------

def test_proficient_just_misses_intercept_count_falls_back_to_mature():
    # 60+ days, 9 intercepts (< 10), positive fitness -> Mature.
    s = _summary(blocks=9, age=70.0)
    assert cgm.classify_one(s) == "Mature"


def test_mature_just_misses_intercept_count_falls_back_to_growing():
    # 30+ days, 4 intercepts (< 5), positive fitness -> Growing because
    # it doesn't meet Mature's intercept threshold but is productive.
    s = _summary(blocks=4, age=30.0)
    assert cgm.classify_one(s) == "Growing"


def test_growing_at_exactly_30_days_with_intercepts():
    s = _summary(blocks=1, age=30.0)
    # 30 days exact: not Inert (intercepts > 0), not Mature (intercepts < 5),
    # so it falls into Growing (productive guard that hasn't matured yet).
    assert cgm.classify_one(s) == "Growing"


def test_fitness_centered_on_block_rate():
    assert cgm.compute_fitness(0.0) == -0.5
    assert cgm.compute_fitness(0.5) == 0.0
    assert cgm.compute_fitness(1.0) == 0.5


# ---------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------

def test_cli_classifies_aggregator_output_via_stdin(monkeypatch, capsys):
    summaries = {
        "g1": _summary(blocks=10, age=90.0),
        "g2": _summary(fail_opens=3, age=10.0),
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(summaries)))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    rc = cgm.main([])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    out = json.loads(captured.out)
    assert out["g1"]["tier"] == "Proficient"
    assert out["g2"]["tier"] == "Harmful"


def test_cli_reads_source_file(tmp_path, capsys):
    payload = {"g1": _summary(blocks=10, age=90.0)}
    src = tmp_path / "agg.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    rc = cgm.main(["--source", str(src)])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["g1"]["tier"] == "Proficient"


def test_cli_treat_unseen_as_inert_flag_propagates(tmp_path, capsys):
    payload = {"g1": _summary(blocks=0, age=None)}
    src = tmp_path / "agg.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    rc = cgm.main(["--source", str(src), "--treat-unseen-as-inert"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["g1"]["tier"] == "Inert"


# ---------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------

def test_cli_bad_source_returns_config_error(tmp_path, capsys):
    rc = cgm.main(["--source", str(tmp_path / "missing.json")])
    captured = capsys.readouterr()
    assert rc == 2
    assert "cannot read aggregator JSON" in captured.err


def test_cli_non_object_input_returns_logic_error(tmp_path, capsys):
    src = tmp_path / "agg.json"
    src.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    rc = cgm.main(["--source", str(src)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "must be an object" in captured.err


def test_classify_pure_function_returns_dict_per_guard():
    summaries = {
        "g1": _summary(blocks=10, age=90.0),
        "g2": _summary(blocks=0, age=45.0),
    }
    out = cgm.classify(summaries)
    assert out["g1"]["tier"] == "Proficient"
    assert out["g2"]["tier"] == "Inert"
    assert "fitness" in out["g1"]
    assert "intercepts" in out["g2"]
