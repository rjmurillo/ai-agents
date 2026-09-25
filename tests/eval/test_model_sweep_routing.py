"""Unit tests for the routing verdict in scripts/eval/_model_sweep_core.py.

Pure comparison core: no I/O, no API. Covers decide_routing (the lightest
sufficient model on a price ladder), its resolved flag, and routing_report.
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
    import _model_sweep_core as core
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


# --- decide_routing --------------------------------------------------------

# A small, test-local price ladder (never the real pricing table): cheap <
# mid < top by input+output list price per 1K tokens.
_ROUTING_PRICES = {
    "cheap": {"input": 0.00005, "output": 0.00005},  # 0.0001
    "mid": {"input": 0.0005, "output": 0.0005},  # 0.001
    "top": {"input": 0.0025, "output": 0.0025},  # 0.005
}


def _routing_result(model_id, rate, *, n=6, **kw):
    """A ModelResult with a constant rate across *n* fixtures (deterministic CI)."""
    return _result(model_id, {f"f{i}": [rate] for i in range(n)}, recall=rate, **kw)


def test_decide_routing_picks_cheapest_when_it_matches_best():
    cheap = _routing_result("cheap", 1.0)
    mid = _routing_result("mid", 0.5)
    top = _routing_result("top", 0.3)
    decision = core.decide_routing([cheap, mid, top], prices=_ROUTING_PRICES)
    assert decision.best_model == "cheap"
    assert decision.lightest_sufficient_model == "cheap"


def test_decide_routing_skips_clearly_trailing_cheap_model():
    cheap = _routing_result("cheap", 0.2)
    mid = _routing_result("mid", 0.95)
    top = _routing_result("top", 1.0)
    decision = core.decide_routing([cheap, mid, top], prices=_ROUTING_PRICES)
    assert decision.best_model == "top"
    assert decision.lightest_sufficient_model == "mid"
    rows = {r["model_id"]: r for r in decision.candidates}
    assert rows["cheap"]["sufficient"] is False
    assert rows["mid"]["sufficient"] is True
    assert rows["top"]["sufficient"] is True


def test_decide_routing_best_qualifies_when_all_cheaper_fail():
    cheap = _routing_result("cheap", 0.2)
    mid = _routing_result("mid", 0.95)
    top = _routing_result("top", 1.0)
    # Tight margin: mid's -0.05 delta no longer clears the bar, only top does.
    decision = core.decide_routing([cheap, mid, top], prices=_ROUTING_PRICES, margin=0.02)
    assert decision.best_model == "top"
    assert decision.lightest_sufficient_model == "top"


def test_decide_routing_ordering_independent_of_input_order():
    cheap = _routing_result("cheap", 1.0)
    mid = _routing_result("mid", 0.9)
    top = _routing_result("top", 0.8)
    d1 = core.decide_routing([cheap, mid, top], prices=_ROUTING_PRICES)
    d2 = core.decide_routing([top, cheap, mid], prices=_ROUTING_PRICES)
    order1 = [r["model_id"] for r in d1.candidates]
    order2 = [r["model_id"] for r in d2.candidates]
    assert order1 == order2 == ["cheap", "mid", "top"]
    assert d1.lightest_sufficient_model == d2.lightest_sufficient_model


def test_decide_routing_tie_on_price_broken_by_model_id():
    prices = dict(_ROUTING_PRICES)
    prices["beta"] = {"input": 0.001, "output": 0.001}
    prices["alpha"] = {"input": 0.001, "output": 0.001}
    beta = _routing_result("beta", 1.0)
    alpha = _routing_result("alpha", 1.0)
    decision = core.decide_routing([beta, alpha], prices=prices)
    order = [r["model_id"] for r in decision.candidates]
    assert order == ["alpha", "beta"]


def test_decide_routing_unpriced_model_raises():
    cheap = _routing_result("cheap", 1.0)
    unpriced = _routing_result("mystery", 0.5)
    with pytest.raises(core.SweepDecisionError, match="no list price"):
        core.decide_routing([cheap, unpriced], prices=_ROUTING_PRICES)


@pytest.mark.parametrize("margin", [-0.1, float("nan")])
def test_decide_routing_rejects_invalid_margin(margin):
    cheap = _routing_result("cheap", 1.0)
    mid = _routing_result("mid", 0.9)
    with pytest.raises(core.SweepDecisionError, match="finite"):
        core.decide_routing([cheap, mid], prices=_ROUTING_PRICES, margin=margin)


def test_decide_routing_below_min_shared_fixtures_raises():
    cheap = _result("cheap", {"f0": [1.0]}, recall=1.0)
    mid = _result("mid", {"f0": [0.9]}, recall=0.9)
    with pytest.raises(core.SweepDecisionError, match="shared stable fixture"):
        core.decide_routing([cheap, mid], prices=_ROUTING_PRICES)


def test_decide_routing_refuses_degraded_result():
    cheap = _routing_result("cheap", 1.0, error_count=1)
    mid = _routing_result("mid", 0.9)
    with pytest.raises(core.SweepDecisionError, match="error_count"):
        core.decide_routing([cheap, mid], prices=_ROUTING_PRICES)


def test_decide_routing_rejects_divergent_fixture_sha():
    cheap = _routing_result("cheap", 1.0, fixture_set_sha="s1")
    mid = _routing_result("mid", 0.9, fixture_set_sha="s2")
    with pytest.raises(core.SweepDecisionError, match="different fixture sets"):
        core.decide_routing([cheap, mid], prices=_ROUTING_PRICES)


def test_decide_routing_empty_results_raises():
    with pytest.raises(core.SweepDecisionError, match="no model results"):
        core.decide_routing([], prices=_ROUTING_PRICES)


def test_routing_report_shape():
    cheap = _routing_result("cheap", 1.0)
    mid = _routing_result("mid", 0.5)
    decision = core.decide_routing([cheap, mid], prices=_ROUTING_PRICES)
    report = core.routing_report(decision)
    assert set(report) == {
        "lightest_sufficient_model",
        "best_model",
        "margin",
        "resolved",
        "candidates",
        "reason",
    }
    assert isinstance(report["candidates"], list)
    row = report["candidates"][0]
    assert set(row) == {
        "model_id",
        "list_price_per_1k",
        "mean_recall",
        "delta_vs_best",
        "ci_low_vs_best",
        "ci_high_vs_best",
        "sufficient",
        "resolved",
    }


def test_decide_routing_keeps_cheap_model_on_small_noisy_gap():
    """A gap inside the margin routes down even when the CI cannot prove it.

    At 8 fixtures a 0.05 gap with fixture-level spread leaves the lower bound
    far below -margin. The verdict still routes down, and marks it unresolved.
    """
    cheap = _result("cheap", {f"f{i}": [1.0 if i % 2 else 0.0] for i in range(8)}, recall=0.5)
    top = _result(
        "top",
        {f"f{i}": [1.0 if i % 2 or i == 0 else 0.0] for i in range(8)},
        recall=0.625,
    )
    decision = core.decide_routing([cheap, top], prices=_ROUTING_PRICES, margin=0.2)
    assert decision.lightest_sufficient_model == "cheap"
    assert decision.best_model == "top"
    assert decision.resolved is False
    assert "not proven" in decision.reason
    cheap_row = next(r for r in decision.candidates if r["model_id"] == "cheap")
    assert cheap_row["ci_low_vs_best"] < -0.2
    assert cheap_row["ci_high_vs_best"] >= cheap_row["ci_low_vs_best"]


def test_decide_routing_resolved_when_cheap_model_matches_on_every_fixture():
    cheap = _routing_result("cheap", 0.9)
    top = _routing_result("top", 0.9)
    decision = core.decide_routing([cheap, top], prices=_ROUTING_PRICES)
    assert decision.lightest_sufficient_model == "cheap"
    assert decision.resolved is True
    assert "non-inferiority proven" in decision.reason


def test_decide_routing_resolved_when_best_is_cheapest():
    cheap = _routing_result("cheap", 1.0)
    top = _routing_result("top", 0.2)
    decision = core.decide_routing([cheap, top], prices=_ROUTING_PRICES)
    assert decision.lightest_sufficient_model == "cheap"
    assert decision.best_model == "cheap"
    assert decision.resolved is True


def test_decide_routing_gap_exactly_at_margin_is_sufficient():
    cheap = _routing_result("cheap", 0.7)
    top = _routing_result("top", 0.8)
    decision = core.decide_routing([cheap, top], prices=_ROUTING_PRICES, margin=0.1)
    assert decision.lightest_sufficient_model == "cheap"
