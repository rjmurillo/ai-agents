"""Model-sweep comparison core for eval-model-sweep.py (Issue #2840).

Pure, side-effect-free logic: no I/O, no subprocess, no API. Given one
``ModelResult`` per candidate model (the ``agent`` variant's per-fixture pass
rates at that model), decide whether any candidate beats the harness-default
model by a margin large enough to *justify keeping a model pin*.

Design (AGENTS.md Software Hierarchy: testability first, separate use from
creation):

    eval-model-sweep.py (CLI, live runs) -> [ModelResult, ...] -> decide() -> SweepDecision

The DECISION is driven by the point-estimate recall delta plus a paired
bootstrap 95% CI on the shared fixture set (the same resample-fixtures method
`_report_aggregator.pairwise_bootstrap_ci` uses for the agent-vs-baseline CI,
reused here across models instead of across prompt variants). Cohen's d_z is
reported as a secondary descriptor only; it is never the gate, so its
zero-variance edge case cannot flip a verdict.

Verdict semantics for Issue #2840:
    KEEP_PIN  -> a specific candidate measurably beats the default; the skill
                 keeps that model pin and cites the sweep artifact.
    DROP_PIN  -> the default ranks first, or the lead is within the noise
                 (CI includes 0) or below ``min_effect``; drop the pin and
                 inherit the harness default (`auto`).
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass

from _report_aggregator import (
    BOOTSTRAP_ITERATIONS,
    CI_LOWER_PERCENTILE,
    CI_UPPER_PERCENTILE,
    _percentile,
)

SCHEMA_VERSION = "1"
DEFAULT_MIN_EFFECT = 0.05
DEFAULT_SEED = 42

DECISION_KEEP = "KEEP_PIN"
DECISION_DROP = "DROP_PIN"


class SweepDecisionError(Exception):
    """Raised when a sweep cannot be decided (e.g. default model absent)."""


@dataclass(frozen=True)
class ModelResult:
    """One candidate model's ``agent``-variant outcome on a fixture set.

    ``per_fixture_agent_rates`` maps ``fixture_id -> [pass_rate_per_run, ...]``
    exactly as ``report.json``'s ``per_fixture_pass_rates[fixture_id]["agent"]``
    carries it. ``agent_recall`` is the report's headline recall for the agent
    variant (carried through verbatim so the point estimate matches the
    single-model report and is not silently redefined here).
    """

    model_id: str
    agent_recall: float
    per_fixture_agent_rates: dict[str, list[float]]
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    error_count: int = 0

    @property
    def fixture_means(self) -> dict[str, float]:
        """Mean pass rate per fixture (over its runs); empty runs score 0.0."""
        return {
            fid: (sum(rates) / len(rates) if rates else 0.0)
            for fid, rates in self.per_fixture_agent_rates.items()
        }


@dataclass(frozen=True)
class SweepDecision:
    """Outcome of comparing candidates against the default model."""

    winner_model: str
    default_model: str
    winner_recall: float
    default_recall: float
    recall_delta: float
    ci95: tuple[float, float]
    cohens_d: float
    decision: str
    reason: str


def _shared_fixture_ids(a: ModelResult, b: ModelResult) -> list[str]:
    """Sorted intersection of fixture ids present for both models."""
    return sorted(set(a.fixture_means) & set(b.fixture_means))


def paired_bootstrap_ci(
    winner: ModelResult,
    default: ModelResult,
    *,
    iterations: int = BOOTSTRAP_ITERATIONS,
    rng: random.Random | None = None,
) -> tuple[float, float]:
    """95% paired bootstrap CI on the per-fixture mean-rate delta (winner - default).

    Resamples the shared fixture ids with replacement; for each resample takes
    the mean of per-fixture ``winner - default`` differences; returns the
    [2.5, 97.5] percentiles of the resampled deltas. Mirrors
    ``_report_aggregator.pairwise_bootstrap_ci`` (fixture-id resampling, same
    percentiles) but compares two *models* rather than two prompt variants.
    """
    ids = _shared_fixture_ids(winner, default)
    if not ids:
        return (0.0, 0.0)
    rng = rng or random.Random(DEFAULT_SEED)
    w_means = winner.fixture_means
    d_means = default.fixture_means
    n = len(ids)
    deltas: list[float] = []
    for _ in range(iterations):
        sample = [ids[rng.randrange(n)] for _ in range(n)]
        delta = sum(w_means[f] - d_means[f] for f in sample) / n
        deltas.append(delta)
    return (
        _percentile(deltas, CI_LOWER_PERCENTILE),
        _percentile(deltas, CI_UPPER_PERCENTILE),
    )


def cohens_d(winner: ModelResult, default: ModelResult) -> float:
    """Paired Cohen's d_z on shared per-fixture mean rates (secondary metric).

    d_z = mean(diff) / stdev(diff). Returns 0.0 when fewer than two shared
    fixtures or when the paired differences have zero spread (the CI, not
    d_z, is the gate, so a degenerate d_z cannot change a verdict).
    """
    ids = _shared_fixture_ids(winner, default)
    if len(ids) < 2:
        return 0.0
    w_means = winner.fixture_means
    d_means = default.fixture_means
    diffs = [w_means[f] - d_means[f] for f in ids]
    spread = statistics.stdev(diffs)
    if spread == 0.0:
        return 0.0
    return statistics.fmean(diffs) / spread


def rank(results: list[ModelResult]) -> list[ModelResult]:
    """Rank by agent_recall descending; break ties by model_id ascending."""
    return sorted(results, key=lambda r: (-r.agent_recall, r.model_id))


def _select_winner(results: list[ModelResult], default_model: str) -> ModelResult:
    """Highest recall; on a tie at the top, prefer the default, else lexical.

    Preferring the incumbent default on a tie is the conservative choice: a
    pin must *beat* the default, not merely match it, to be justified.
    """
    top_recall = max(r.agent_recall for r in results)
    tied = [r for r in results if r.agent_recall == top_recall]
    for r in tied:
        if r.model_id == default_model:
            return r
    return min(tied, key=lambda r: r.model_id)


def decide(
    results: list[ModelResult],
    *,
    default_model: str,
    min_effect: float = DEFAULT_MIN_EFFECT,
    rng: random.Random | None = None,
) -> SweepDecision:
    """Decide KEEP_PIN vs DROP_PIN for a set of candidate model results.

    KEEP_PIN iff a non-default candidate leads by at least ``min_effect`` AND
    the paired bootstrap CI on the recall delta excludes zero. Otherwise
    DROP_PIN (default wins/ties, or the lead is within noise).
    """
    if not results:
        raise SweepDecisionError("no model results to decide on")
    by_id = {r.model_id: r for r in results}
    if default_model not in by_id:
        raise SweepDecisionError(
            f"default model {default_model!r} not among swept models "
            f"{sorted(by_id)}; include it as a candidate to anchor the comparison"
        )
    default = by_id[default_model]
    winner = _select_winner(results, default_model)

    if winner.model_id == default_model:
        return SweepDecision(
            winner_model=default_model,
            default_model=default_model,
            winner_recall=default.agent_recall,
            default_recall=default.agent_recall,
            recall_delta=0.0,
            ci95=(0.0, 0.0),
            cohens_d=0.0,
            decision=DECISION_DROP,
            reason=(
                f"harness default {default_model!r} ranks first "
                f"(recall={default.agent_recall:.4f}); no candidate beats it, "
                f"so no model pin is justified"
            ),
        )

    delta = winner.agent_recall - default.agent_recall
    ci_low, ci_high = paired_bootstrap_ci(winner, default, rng=rng)
    d = cohens_d(winner, default)
    significant = ci_low > 0.0
    material = delta >= min_effect
    keep = significant and material

    if keep:
        reason = (
            f"candidate {winner.model_id!r} beats default {default_model!r} by "
            f"recall_delta={delta:.4f} (>= min_effect={min_effect:.4f}); "
            f"95% CI [{ci_low:.4f}, {ci_high:.4f}] excludes 0; keep this pin "
            f"and cite the sweep artifact"
        )
    elif not significant:
        reason = (
            f"candidate {winner.model_id!r} leads by recall_delta={delta:.4f} "
            f"but 95% CI [{ci_low:.4f}, {ci_high:.4f}] includes 0 (within noise); "
            f"drop the pin and inherit the harness default"
        )
    else:
        reason = (
            f"candidate {winner.model_id!r} leads by recall_delta={delta:.4f} "
            f"below min_effect={min_effect:.4f}; not material enough to justify "
            f"a pin; drop it and inherit the harness default"
        )

    return SweepDecision(
        winner_model=winner.model_id,
        default_model=default_model,
        winner_recall=winner.agent_recall,
        default_recall=default.agent_recall,
        recall_delta=delta,
        ci95=(ci_low, ci_high),
        cohens_d=d,
        decision=DECISION_KEEP if keep else DECISION_DROP,
        reason=reason,
    )


def build_report(
    *,
    agent: str,
    fixtures_sha: str,
    results: list[ModelResult],
    decision: SweepDecision,
    min_effect: float,
    seed: int,
) -> dict:
    """Machine-readable sweep artifact.

    Downstream consumers (Issue #2840): the CI governance check that fails a
    ``model:`` pin lacking a linked sweep artifact, and the pin-migration that
    strips DROP_PIN pins. Field names are stable; ``schema_version`` gates
    future shape changes.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "agent": agent,
        "fixtures_sha": fixtures_sha,
        "default_model": decision.default_model,
        "min_effect": min_effect,
        "seed": seed,
        "models": [
            {
                "model_id": r.model_id,
                "agent_recall": round(r.agent_recall, 6),
                "n_fixtures": len(r.per_fixture_agent_rates),
                "tokens_in": r.tokens_in,
                "tokens_out": r.tokens_out,
                "cost_usd": round(r.cost_usd, 4),
                "error_count": r.error_count,
            }
            for r in rank(results)
        ],
        "winner": decision.winner_model,
        "recall_delta": round(decision.recall_delta, 6),
        "ci95": [round(decision.ci95[0], 6), round(decision.ci95[1], 6)],
        "cohens_d": round(decision.cohens_d, 6),
        "decision": decision.decision,
        "reason": decision.reason,
    }
