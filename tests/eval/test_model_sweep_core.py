"""Unit tests for scripts/eval/_model_sweep_core.py (Issue #2840).

Pure comparison core: no I/O, no API. Covers the KEEP_PIN/DROP_PIN decision
gate, the paired bootstrap CI, Cohen's d_z edge cases, ranking/tie-breaking,
the artifact shape, and the SweepDecisionError guards.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"

# _model_sweep_core imports sibling modules via plain `from X import Y`, so
# EVAL_DIR must be on sys.path while it loads. Scope the mutation to the load
# and remove it afterward so we do not change import resolution for other
# test modules.
_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    import _model_sweep_core as core  # noqa: E402
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))


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
    with pytest.raises(core.SweepDecisionError, match="different fixture sets"):
        core.check_comparable([a, b])


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
        seed=7,
    )
    assert decision.decision == core.DECISION_KEEP
    assert decision.winner_model == "solid"
    assert decision.ci95[0] > 0.0


def test_decide_empty_results_raises():
    with pytest.raises(core.SweepDecisionError):
        core.decide([], default_model="default")


def test_decide_default_absent_raises():
    r = _result("other", {"f1": [1.0]}, recall=1.0)
    with pytest.raises(core.SweepDecisionError, match="default model"):
        core.decide([r], default_model="default")


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
        seed=1,
    )
    assert decision.decision == core.DECISION_KEEP
    assert decision.winner_model == "candidate"
    assert decision.ci95[0] > 0.0
    assert decision.recall_delta >= 0.05
    # On KEEP the winner IS the best candidate, so the two describe the same model.
    assert decision.best_candidate_model == "candidate"
    assert decision.best_candidate_delta == decision.recall_delta


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
        seed=1,
    )
    # 0.02 lead is real (CI excludes 0) but below min_effect -> drop.
    assert decision.decision == core.DECISION_DROP
    assert "below min_effect" in decision.reason
    # DROP means the default wins, so the top-level effect stats describe the
    # winner (default) and MUST be zeroed; the leading candidate's real lead is
    # preserved separately so the artifact stays consistent (Issue #2840).
    assert decision.winner_model == "default"
    assert decision.recall_delta == 0.0
    assert decision.ci95 == (0.0, 0.0)
    assert decision.cohens_d == 0.0
    assert decision.best_candidate_model == "candidate"
    assert decision.best_candidate_delta > 0.0


def test_decide_drops_pin_when_ci_includes_zero():
    # Candidate leads on mean recall but the lead is concentrated in a minority
    # of fixtures, so the paired bootstrap CI straddles 0. This enters the
    # positive-but-noisy DROP branch: the default wins (top-level effect zeroed)
    # while the challenger's real lead is preserved in best_candidate_*.
    default = _result("default", {f"f{i}": [0.30] for i in range(8)})
    candidate = _result(
        "candidate",
        {f"f{i}": ([1.0] if i < 2 else [0.30]) for i in range(8)},
    )
    decision = core.decide(
        [default, candidate],
        default_model="default",
        min_effect=0.0,
        seed=3,
    )
    assert decision.decision == core.DECISION_DROP
    assert "within noise" in decision.reason
    assert decision.winner_model == "default"
    # Winner (default) drives the top-level effect stats -> all zero.
    assert decision.recall_delta == 0.0
    assert decision.ci95 == (0.0, 0.0)
    # The challenger genuinely led on mean recall, but its CI straddles 0.
    assert decision.best_candidate_model == "candidate"
    assert decision.best_candidate_delta > 0.0
    assert decision.best_candidate_ci95[0] <= 0.0 <= decision.best_candidate_ci95[1]


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
    default = _result(
        "default", {"f1": [0.5], "f2": [0.5]}, recall=0.5, tokens_in=10, tokens_out=20
    )
    candidate = _result(
        "candidate",
        {"f1": [0.9], "f2": [0.9]},
        recall=0.9,
        cost_usd=0.1234567,
        error_count=1,
    )
    decision = core.decide([default, candidate], default_model="default", seed=1)
    report = core.build_report(
        agent="security",
        fixtures_sha="abc123",
        results=[default, candidate],
        decision=decision,
        min_effect=0.05,
        seed=42,
    )
    assert report["schemaVersion"] == core.SCHEMA_VERSION
    assert report["agent"] == "security"
    assert report["fixtures_sha"] == "abc123"
    assert report["default_model"] == "default"
    assert report["winner"] == decision.winner_model
    assert report["decision"] == decision.decision
    assert report["n_shared_fixtures"] == 2
    assert [m["model_id"] for m in report["models"]] == ["candidate", "default"]
    assert report["models"][0]["mean_recall"] == 0.9
    assert report["models"][0]["agent_recall"] == 0.9
    assert report["models"][1]["tokens_in"] == 10
    assert report["models"][0]["error_count"] == 1
    assert len(report["ci95"]) == 2
    assert report["best_candidate_model"] == decision.best_candidate_model
    assert len(report["best_candidate_ci95"]) == 2


def test_common_fixture_ids_empty_model_yields_no_shared():
    # R3 F2: a model with no stable fixtures collapses the intersection instead
    # of being silently dropped from it (which previously KeyError'd downstream).
    a = _result("a", {"f1": [1.0]}, recall=1.0)
    b = _result("b", {}, recall=0.0)
    assert core.common_fixture_ids([a, b]) == []


def test_decide_empty_fixture_model_raises():
    # R3 F2 regression: an empty-fixture candidate must hit the no-shared config
    # error, not crash in mean_recall_on with a KeyError.
    default = _result("default", {"f1": [0.5], "f2": [0.5]}, recall=0.5)
    empty = _result("empty", {}, recall=0.0)
    with pytest.raises(core.SweepDecisionError, match="shared"):
        core.decide([default, empty], default_model="default")


def test_decide_single_shared_fixture_drops():
    # R3 F3 regression: one shared fixture makes the bootstrap CI degenerate
    # ([delta, delta]); never KEEP a pin on that. Floor forces DROP.
    default = _result("default", {"f1": [0.1]}, recall=0.1)
    candidate = _result("candidate", {"f1": [0.9]}, recall=0.9)
    decision = core.decide([default, candidate], default_model="default", seed=1)
    assert decision.decision == core.DECISION_DROP
    assert decision.winner_model == "default"
    assert "floor" in decision.reason


def test_decide_is_order_independent():
    # R3 F1 regression: per-candidate seeding makes the verdict (and each CI)
    # invariant to candidate order, so --models ordering cannot flip it.
    default = _result("default", {f"f{i}": [0.30] for i in range(8)})
    noisy = _result("noisy", {f"f{i}": ([1.0] if i < 2 else [0.30]) for i in range(8)})
    solid = _result("solid", {f"f{i}": [0.42] for i in range(8)})
    d1 = core.decide([default, noisy, solid], default_model="default", seed=11)
    d2 = core.decide([default, solid, noisy], default_model="default", seed=11)
    d3 = core.decide([solid, default, noisy], default_model="default", seed=11)
    assert d1.decision == d2.decision == d3.decision
    assert d1.winner_model == d2.winner_model == d3.winner_model
    assert d1.ci95 == d2.ci95 == d3.ci95


def test_paired_bootstrap_ci_bonferroni_widens_lower_bound():
    # R3 F4: the Bonferroni knob (smaller lower percentile) must widen the CI,
    # i.e. push the lower bound down, so sweeping more candidates raises the bar.
    w = _result("w", {f"f{i}": ([1.0] if i < 6 else [0.0]) for i in range(8)})
    d = _result("d", {f"f{i}": [0.3] for i in range(8)})
    ids = core.common_fixture_ids([w, d])
    wide = core.paired_bootstrap_ci(
        w, d, ids, lower_percentile=2.5 / 3, upper_percentile=100 - 2.5 / 3
    )
    narrow = core.paired_bootstrap_ci(
        w, d, ids, lower_percentile=2.5, upper_percentile=97.5
    )
    assert wide[0] <= narrow[0]
