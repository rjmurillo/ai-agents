"""Unit tests for scripts/eval/_model_sweep_core.py (Issue #2840).

Pure comparison core: no I/O, no API. Covers the KEEP_PIN/DROP_PIN decision
gate, the paired bootstrap CI, Cohen's d_z edge cases, ranking/tie-breaking,
the artifact shape, and the SweepDecisionError guards.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _model_sweep_core as core  # noqa: E402


def _result(model_id, rates, *, recall=None, **kw):
    """Build a ModelResult; recall defaults to the mean of all per-fixture means."""
    means = [sum(v) / len(v) if v else 0.0 for v in rates.values()] if rates else []
    if recall is None:
        recall = sum(means) / len(means) if means else 0.0
    return core.ModelResult(
        model_id=model_id,
        agent_recall=recall,
        per_fixture_agent_rates=rates,
        **kw,
    )


def test_check_comparable_passes_matching_sha():
    a = _result("a", {"f": [1.0]}, recall=1.0, fixture_set_sha="s")
    b = _result("b", {"f": [0.5]}, recall=0.5, fixture_set_sha="s")
    core.check_comparable([a, b])  # no raise


def test_check_comparable_ignores_empty_sha():
    a = _result("a", {"f": [1.0]}, recall=1.0)
    b = _result("b", {"f": [0.5]}, recall=0.5)
    core.check_comparable([a, b])  # empty shas ignored -> no raise


def test_check_comparable_rejects_divergent_sha():
    a = _result("a", {"f": [1.0]}, recall=1.0, fixture_set_sha="s1")
    b = _result("b", {"f": [0.5]}, recall=0.5, fixture_set_sha="s2")
    try:
        core.check_comparable([a, b])
    except core.SweepDecisionError as exc:
        assert "different fixture sets" in str(exc)
        return
    raise AssertionError("expected SweepDecisionError for divergent fixture shas")


def test_fixture_means_empty_runs_score_zero():
    r = _result("m", {"f1": [1.0, 0.0], "f2": []}, recall=0.5)
    assert r.fixture_means == {"f1": 0.5, "f2": 0.0}


def test_rank_orders_by_recall_then_id():
    a = _result("b-model", {"f": [0.9]}, recall=0.9)
    b = _result("a-model", {"f": [0.9]}, recall=0.9)
    c = _result("c-model", {"f": [0.5]}, recall=0.5)
    ids = core.common_fixture_ids([a, b, c])
    ranked = core.rank([c, a, b], ids)
    assert [r.model_id for r in ranked] == ["a-model", "b-model", "c-model"]


def test_decide_picks_qualifying_second_candidate_over_noisy_top():
    # R2-1 regression: the top point-estimate model is noisy (its lead is
    # concentrated in a minority of fixtures, so the paired CI straddles 0)
    # and does NOT qualify. A lower-point-estimate candidate that beats the
    # default consistently DOES qualify and must not be suppressed.
    default = _result("default", {f"f{i}": [0.30] for i in range(8)})
    # Noisy top: mean 0.475 (highest) but the lead lives in only 2 fixtures.
    noisy_top = _result(
        "noisy-top",
        {f"f{i}": ([1.0] if i < 2 else [0.30]) for i in range(8)},
    )
    # Solid: mean 0.42 (lower) but beats default on EVERY fixture -> CI > 0.
    solid = _result("solid", {f"f{i}": [0.42] for i in range(8)})
    decision = core.decide(
        [default, noisy_top, solid],
        default_model="default",
        min_effect=0.05,
        rng=random.Random(7),
    )
    assert decision.decision == core.DECISION_KEEP
    assert decision.winner_model == "solid"
    assert decision.ci95[0] > 0.0


def test_decide_empty_results_raises():
    try:
        core.decide([], default_model="default")
    except core.SweepDecisionError:
        return
    raise AssertionError("expected SweepDecisionError for empty results")


def test_decide_default_absent_raises():
    r = _result("other", {"f1": [1.0]}, recall=1.0)
    try:
        core.decide([r], default_model="default")
    except core.SweepDecisionError as exc:
        assert "default model" in str(exc)
        return
    raise AssertionError("expected SweepDecisionError when default is absent")


def test_decide_default_wins_drops_pin():
    default = _result("default", {"f1": [0.9], "f2": [0.9]}, recall=0.9)
    weaker = _result("other", {"f1": [0.5], "f2": [0.5]}, recall=0.5)
    decision = core.decide([default, weaker], default_model="default")
    assert decision.decision == core.DECISION_DROP
    assert decision.winner_model == "default"
    assert decision.recall_delta == 0.0


def test_decide_keeps_pin_on_large_consistent_lead():
    # Candidate beats default on every shared fixture by a wide, consistent
    # margin -> delta >> min_effect and the paired CI excludes 0.
    default = _result(
        "default",
        {f"f{i}": [0.1] for i in range(8)},
        recall=0.1,
    )
    candidate = _result(
        "candidate",
        {f"f{i}": [0.9] for i in range(8)},
        recall=0.9,
    )
    decision = core.decide(
        [default, candidate],
        default_model="default",
        rng=random.Random(1),
    )
    assert decision.decision == core.DECISION_KEEP
    assert decision.winner_model == "candidate"
    assert decision.ci95[0] > 0.0
    assert decision.recall_delta >= 0.05


def test_decide_drops_pin_when_lead_below_min_effect():
    default = _result(
        "default",
        {f"f{i}": [0.80] for i in range(8)},
        recall=0.80,
    )
    candidate = _result(
        "candidate",
        {f"f{i}": [0.82] for i in range(8)},
        recall=0.82,
    )
    decision = core.decide(
        [default, candidate],
        default_model="default",
        min_effect=0.05,
        rng=random.Random(1),
    )
    # 0.02 lead is real (CI excludes 0) but below min_effect -> drop.
    assert decision.decision == core.DECISION_DROP
    assert "below min_effect" in decision.reason


def test_decide_drops_pin_when_ci_includes_zero():
    # Candidate wins on point recall but the per-fixture signal is noisy:
    # it beats default on half the fixtures and loses on the other half, so
    # the paired CI straddles 0 even though the headline recall is higher.
    default = _result(
        "default",
        {"a": [0.0], "b": [1.0], "c": [0.0], "d": [1.0]},
        recall=0.50,
    )
    candidate = _result(
        "candidate",
        {"a": [1.0], "b": [0.0], "c": [1.0], "d": [0.0]},
        recall=0.60,
    )
    decision = core.decide(
        [default, candidate],
        default_model="default",
        min_effect=0.0,
        rng=random.Random(3),
    )
    assert decision.decision == core.DECISION_DROP
    assert decision.ci95[0] <= 0.0 <= decision.ci95[1]


def test_paired_bootstrap_ci_no_shared_fixtures_is_zero():
    w = _result("w", {"a": [1.0]}, recall=1.0)
    d = _result("d", {"b": [0.0]}, recall=0.0)
    ids = core.common_fixture_ids([w, d])
    assert core.paired_bootstrap_ci(w, d, ids) == (0.0, 0.0)


def test_cohens_d_fewer_than_two_fixtures_is_zero():
    w = _result("w", {"a": [1.0]}, recall=1.0)
    d = _result("d", {"a": [0.0]}, recall=0.0)
    assert core.cohens_d(w, d, ["a"]) == 0.0


def test_cohens_d_zero_variance_is_zero():
    # Constant per-fixture difference -> stdev(diffs) == 0 -> guarded to 0.0.
    w = _result("w", {"a": [0.6], "b": [0.6]}, recall=0.6)
    d = _result("d", {"a": [0.5], "b": [0.5]}, recall=0.5)
    assert core.cohens_d(w, d, ["a", "b"]) == 0.0


def test_cohens_d_nonzero_when_diffs_vary():
    w = _result("w", {"a": [0.9], "b": [0.6]}, recall=0.75)
    d = _result("d", {"a": [0.1], "b": [0.5]}, recall=0.30)
    assert core.cohens_d(w, d, ["a", "b"]) > 0.0


def test_build_report_shape():
    default = _result("default", {"f1": [0.5]}, recall=0.5, tokens_in=10, tokens_out=20)
    candidate = _result(
        "candidate", {"f1": [0.9]}, recall=0.9, cost_usd=0.1234567, error_count=1
    )
    decision = core.decide(
        [default, candidate], default_model="default", rng=random.Random(1)
    )
    report = core.build_report(
        agent="security",
        fixtures_sha="abc123",
        results=[default, candidate],
        decision=decision,
        min_effect=0.05,
        seed=42,
    )
    assert report["schema_version"] == core.SCHEMA_VERSION
    assert report["agent"] == "security"
    assert report["fixtures_sha"] == "abc123"
    assert report["default_model"] == "default"
    assert report["winner"] == decision.winner_model
    assert report["decision"] == decision.decision
    assert [m["model_id"] for m in report["models"]] == ["candidate", "default"]
    assert report["models"][1]["tokens_in"] == 10
    assert report["models"][0]["error_count"] == 1
    assert len(report["ci95"]) == 2
