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

import hashlib
import random
import statistics
from dataclasses import dataclass

from _report_aggregator import (
    BOOTSTRAP_ITERATIONS,
    CI_LOWER_PERCENTILE,
    CI_UPPER_PERCENTILE,
)


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (local copy; no numpy).

    Duplicated from ``_report_aggregator`` deliberately: importing that
    module's private ``_percentile`` coupled the sweep to an internal helper
    that could change without a contract. The math is a stable, standard
    definition, so an independent copy is safer than the private dependency.
    """
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    rank = (pct / 100.0) * (len(s) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(s) - 1)
    frac = rank - lower
    return s[lower] + frac * (s[upper] - s[lower])

SCHEMA_VERSION = "1"
DEFAULT_MIN_EFFECT = 0.05
DEFAULT_SEED = 42

# A paired bootstrap over fewer than two shared fixtures is degenerate: every
# resample draws the same fixture(s), so the CI collapses onto the point delta
# and stops being evidence. Below this floor we never KEEP a pin.
MIN_SHARED_FIXTURES = 2

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
    fixture_set_sha: str = ""

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
    # The top-level recall_delta/ci95/cohens_d always describe winner_model vs
    # the default (so a DROP_PIN with the default winning reports 0/[0,0]/0).
    # The leading candidate's stats, when the default wins, live in the
    # best_candidate_* fields so the artifact stays machine-readable without
    # conflating "winner" with "best challenger".
    best_candidate_model: str | None = None
    best_candidate_delta: float = 0.0
    best_candidate_ci95: tuple[float, float] = (0.0, 0.0)
    best_candidate_cohens_d: float = 0.0


def check_comparable(results: list[ModelResult]) -> None:
    """Reject a sweep whose models ran on different fixture sets.

    Every model must evaluate the SAME input fixtures for the cross-model
    delta and CI to mean anything. The base evaluator records the input set
    as ``fixture_set_sha``; if two models carry different (non-empty) shas the
    sweep pointed them at different fixtures and the comparison is invalid.
    Empty shas (e.g. injected test doubles) are ignored.
    """
    shas = {r.fixture_set_sha for r in results if r.fixture_set_sha}
    if len(shas) > 1:
        raise SweepDecisionError(
            "models were evaluated on different fixture sets "
            f"(fixture_set_sha values {sorted(shas)}); sweep all models over "
            "the same --fixtures so the comparison is valid"
        )


def common_fixture_ids(results: list[ModelResult]) -> list[str]:
    """Sorted intersection of fixture ids present (and stable) for every model.

    ``per_fixture_agent_rates`` is already flaky-excluded upstream, so the
    intersection is the set of fixtures that are stable across ALL swept
    models. Comparing on this common set keeps every model's recall, the
    cross-model delta, and the bootstrap CI on the same fixtures even when
    individual models excluded different flaky fixtures.
    """
    if not results:
        return []
    sets = [set(r.per_fixture_agent_rates) for r in results]
    return sorted(set.intersection(*sets))


def mean_recall_on(result: ModelResult, ids: list[str]) -> float:
    """Unweighted mean per-fixture pass rate over *ids* (the sweep metric).

    This is the single estimand used for BOTH the point delta and the
    bootstrap CI, so the KEEP/DROP gate never mixes metrics. It weights each
    fixture equally (unlike the report's assertion-weighted ``agent_recall``,
    which is retained only as an informational per-model field).
    """
    if not ids:
        return 0.0
    means = result.fixture_means
    return sum(means[f] for f in ids) / len(ids)


def paired_bootstrap_ci(
    winner: ModelResult,
    default: ModelResult,
    ids: list[str],
    *,
    iterations: int = BOOTSTRAP_ITERATIONS,
    rng: random.Random | None = None,
    lower_percentile: float = CI_LOWER_PERCENTILE,
    upper_percentile: float = CI_UPPER_PERCENTILE,
) -> tuple[float, float]:
    """Paired bootstrap CI on the per-fixture mean-rate delta (winner - default).

    Resamples *ids* (the common stable fixture set) with replacement; for each
    resample takes the mean of per-fixture ``winner - default`` differences;
    returns the [``lower_percentile``, ``upper_percentile``] percentiles of the
    resampled deltas. Mirrors ``_report_aggregator.pairwise_bootstrap_ci``
    (fixture-id resampling), computed on the same fixtures and metric as the
    point delta. The percentiles default to the two-sided 95% interval but are
    widened by ``decide`` for a family-wise (Bonferroni) correction when more
    than one candidate is swept.
    """
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
        _percentile(deltas, lower_percentile),
        _percentile(deltas, upper_percentile),
    )


def cohens_d(winner: ModelResult, default: ModelResult, ids: list[str]) -> float:
    """Paired Cohen's d_z on the *ids* per-fixture mean rates (secondary metric).

    d_z = mean(diff) / stdev(diff). Returns 0.0 when fewer than two shared
    fixtures or when the paired differences have zero spread (the CI, not
    d_z, is the gate, so a degenerate d_z cannot change a verdict).
    """
    if len(ids) < 2:
        return 0.0
    w_means = winner.fixture_means
    d_means = default.fixture_means
    diffs = [w_means[f] - d_means[f] for f in ids]
    spread = statistics.stdev(diffs)
    if spread == 0.0:
        return 0.0
    return statistics.fmean(diffs) / spread


def rank(results: list[ModelResult], ids: list[str]) -> list[ModelResult]:
    """Rank by mean recall on *ids* descending; break ties by model_id ascending."""
    return sorted(results, key=lambda r: (-mean_recall_on(r, ids), r.model_id))


def _candidate_rng(seed: int, default_model: str, candidate_id: str) -> random.Random:
    """Independent, deterministic RNG keyed by (seed, default, candidate).

    Each candidate's bootstrap stream is derived from its own id, not from a
    single RNG advanced in candidate order. This makes the verdict independent
    of the order candidates appear in (e.g. the ``--models`` argument order),
    while staying fully reproducible for a given seed.
    """
    digest = hashlib.sha256(
        f"{seed}:{default_model}:{candidate_id}".encode()
    ).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _evaluate_candidate(
    candidate: ModelResult,
    default: ModelResult,
    ids: list[str],
    *,
    min_effect: float,
    rng: random.Random,
    lower_percentile: float,
) -> tuple[float, tuple[float, float], bool]:
    """Return (delta, ci, qualifies) for one candidate vs the default.

    ``qualifies`` iff the candidate leads by at least ``min_effect`` mean
    recall AND the (family-wise-adjusted) paired bootstrap CI on the delta
    excludes 0.
    """
    delta = mean_recall_on(candidate, ids) - mean_recall_on(default, ids)
    ci_low, ci_high = paired_bootstrap_ci(
        candidate,
        default,
        ids,
        rng=rng,
        lower_percentile=lower_percentile,
        upper_percentile=100.0 - lower_percentile,
    )
    qualifies = delta >= min_effect and ci_low > 0.0
    return delta, (ci_low, ci_high), qualifies


def decide(
    results: list[ModelResult],
    *,
    default_model: str,
    min_effect: float = DEFAULT_MIN_EFFECT,
    seed: int = DEFAULT_SEED,
) -> SweepDecision:
    """Decide KEEP_PIN vs DROP_PIN for a set of candidate model results.

    Every non-default candidate is evaluated against the default on the common
    stable fixture set. KEEP_PIN iff at least one candidate leads by
    ``min_effect`` mean recall AND its paired bootstrap CI excludes 0; the
    strongest such qualifier wins the pin. Otherwise DROP_PIN (a higher
    point-estimate but noisy candidate cannot force a KEEP, and it cannot
    suppress a solid lower-ranked candidate either).

    The verdict is independent of candidate order: each candidate's bootstrap
    stream is seeded from its own id (not a single RNG advanced in order). When
    more than one candidate is swept the per-candidate CIs are Bonferroni-
    widened so the family-wise false-KEEP rate stays near 5% instead of
    compounding with the number of candidates.
    """
    if not results:
        raise SweepDecisionError("no model results to decide on")
    check_comparable(results)
    by_id = {r.model_id: r for r in results}
    if default_model not in by_id:
        raise SweepDecisionError(
            f"default model {default_model!r} not among swept models "
            f"{sorted(by_id)}; include it as a candidate to anchor the comparison"
        )
    default = by_id[default_model]
    ids = common_fixture_ids(results)
    if not ids:
        raise SweepDecisionError(
            "no fixtures are shared and stable across all swept models; cannot "
            "compare (check per-model flaky exclusions and the --fixtures set)"
        )
    default_recall = mean_recall_on(default, ids)
    candidates = [r for r in results if r.model_id != default_model]

    if len(ids) < MIN_SHARED_FIXTURES:
        return SweepDecision(
            winner_model=default_model,
            default_model=default_model,
            winner_recall=default_recall,
            default_recall=default_recall,
            recall_delta=0.0,
            ci95=(0.0, 0.0),
            cohens_d=0.0,
            decision=DECISION_DROP,
            reason=(
                f"only {len(ids)} shared stable fixture(s) across all swept "
                f"models, below the {MIN_SHARED_FIXTURES}-fixture floor for a "
                f"meaningful bootstrap CI; cannot justify a pin, inherit the "
                f"harness default (widen the shared --fixtures set to decide)"
            ),
        )

    # Bonferroni: split the family-wise 5% two-sided alpha across candidates so
    # sweeping many models does not inflate the false-KEEP rate.
    lower_percentile = CI_LOWER_PERCENTILE / max(len(candidates), 1)

    evaluated: list[tuple[ModelResult, float, tuple[float, float], bool]] = []
    for cand in candidates:
        delta, ci, qualifies = _evaluate_candidate(
            cand,
            default,
            ids,
            min_effect=min_effect,
            rng=_candidate_rng(seed, default_model, cand.model_id),
            lower_percentile=lower_percentile,
        )
        evaluated.append((cand, delta, ci, qualifies))

    qualifiers = [e for e in evaluated if e[3]]
    if qualifiers:
        cand, delta, ci, _ = sorted(
            qualifiers,
            key=lambda e: (-e[1], -mean_recall_on(e[0], ids), e[0].model_id),
        )[0]
        return SweepDecision(
            winner_model=cand.model_id,
            default_model=default_model,
            winner_recall=mean_recall_on(cand, ids),
            default_recall=default_recall,
            recall_delta=delta,
            ci95=ci,
            cohens_d=cohens_d(cand, default, ids),
            decision=DECISION_KEEP,
            reason=(
                f"candidate {cand.model_id!r} beats default {default_model!r} by "
                f"mean-recall delta={delta:.4f} (>= min_effect={min_effect:.4f}) "
                f"over {len(ids)} shared fixtures; family-wise CI [{ci[0]:.4f}, "
                f"{ci[1]:.4f}] excludes 0; keep this pin and cite the artifact"
            ),
            best_candidate_model=cand.model_id,
            best_candidate_delta=delta,
            best_candidate_ci95=ci,
            best_candidate_cohens_d=cohens_d(cand, default, ids),
        )

    positive = [e for e in evaluated if e[1] > 0.0]
    if positive:
        cand, delta, ci, _ = sorted(positive, key=lambda e: (-e[1], e[0].model_id))[0]
        if ci[0] <= 0.0:
            reason = (
                f"best candidate {cand.model_id!r} leads by mean-recall "
                f"delta={delta:.4f} but family-wise CI [{ci[0]:.4f}, {ci[1]:.4f}] "
                f"includes 0 (within noise); drop the pin and inherit the default"
            )
        else:
            reason = (
                f"best candidate {cand.model_id!r} leads by mean-recall "
                f"delta={delta:.4f} below min_effect={min_effect:.4f}; not "
                f"material enough to justify a pin; drop it and inherit the default"
            )
        return SweepDecision(
            winner_model=default_model,
            default_model=default_model,
            winner_recall=default_recall,
            default_recall=default_recall,
            recall_delta=0.0,
            ci95=(0.0, 0.0),
            cohens_d=0.0,
            decision=DECISION_DROP,
            reason=reason,
            best_candidate_model=cand.model_id,
            best_candidate_delta=delta,
            best_candidate_ci95=ci,
            best_candidate_cohens_d=cohens_d(cand, default, ids),
        )

    return SweepDecision(
        winner_model=default_model,
        default_model=default_model,
        winner_recall=default_recall,
        default_recall=default_recall,
        recall_delta=0.0,
        ci95=(0.0, 0.0),
        cohens_d=0.0,
        decision=DECISION_DROP,
        reason=(
            f"harness default {default_model!r} ranks first over {len(ids)} "
            f"shared fixtures (mean recall={default_recall:.4f}); no candidate "
            f"beats it, so no model pin is justified"
        ),
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
    strips DROP_PIN pins. Field names are stable; ``schemaVersion`` gates
    future shape changes (name matches the harness report convention in
    ``_report_writer.py``).
    """
    ids = common_fixture_ids(results)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "agent": agent,
        "fixtures_sha": fixtures_sha,
        "default_model": decision.default_model,
        "min_effect": min_effect,
        "seed": seed,
        "n_shared_fixtures": len(ids),
        "models": [
            {
                "model_id": r.model_id,
                "mean_recall": round(mean_recall_on(r, ids), 6),
                "agent_recall": round(r.agent_recall, 6),
                "n_fixtures": len(r.per_fixture_agent_rates),
                "tokens_in": r.tokens_in,
                "tokens_out": r.tokens_out,
                "cost_usd": round(r.cost_usd, 4),
                "error_count": r.error_count,
            }
            for r in rank(results, ids)
        ],
        "winner": decision.winner_model,
        "recall_delta": round(decision.recall_delta, 6),
        "ci95": [round(decision.ci95[0], 6), round(decision.ci95[1], 6)],
        "cohens_d": round(decision.cohens_d, 6),
        "best_candidate_model": decision.best_candidate_model,
        "best_candidate_delta": round(decision.best_candidate_delta, 6),
        "best_candidate_ci95": [
            round(decision.best_candidate_ci95[0], 6),
            round(decision.best_candidate_ci95[1], 6),
        ],
        "best_candidate_cohens_d": round(decision.best_candidate_cohens_d, 6),
        "decision": decision.decision,
        "reason": decision.reason,
    }
