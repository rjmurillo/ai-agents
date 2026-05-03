"""ReportAggregator: recall, bootstrap CI, distribution, flakiness.

DESIGN-004 §5.6 / REQ-004 AC-2, AC-3, AC-5, AC-10.

Recall = sum(passed_assertions) / sum(total_assertions). Denominator is
the total assertion count, not the fixture count. Errors are counted as
failed assertions in `recall_with_errors` and excluded from the denominator
in `recall_excluding_errors`.

Paired bootstrap: resample fixture ids with replacement at each iteration,
recompute the agent and baseline recall on the resampled set, take the
delta. Repeat n=10000 times. The 95% CI is the [2.5, 97.5] percentile of
the resampled deltas.

This module does NOT reuse `_eval_common.aggregate_multi_run_scores`. That
helper averages LLM-judge dimensional scores; binary pass/fail recall has a
different shape. See REQ-004 dependencies note.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable

from _eval_agent_types import RunRecord
from _eval_common import (
    MODEL_PRICING_RATES_USD_PER_1K_TOKENS,
    PRICING_RATE_AS_OF,
)

BOOTSTRAP_ITERATIONS = 10000
CI_LOWER_PERCENTILE = 2.5
CI_UPPER_PERCENTILE = 97.5
FLAKY_FIXTURE_HALT_FRACTION = 0.30
CONTINGENCY_PERSISTENT_THRESHOLD = 2  # >=2 of 5 reps → flaky=true


@dataclass(frozen=True)
class _AssertionTally:
    """Aggregated counts for one (fixture, variant) tuple across N runs."""

    passed: int
    total: int
    error_runs: int


@dataclass
class AggregateResult:
    """Output of ReportAggregator. Consumed by ReportWriter."""

    agent_recall: float
    baseline_recall: float
    recall_delta: float
    bootstrap_ci_95: tuple[float, float]
    recall_with_errors: float
    recall_excluding_errors: float
    per_fixture_pass_rates: dict[str, dict[str, list[float]]]
    flakiness: bool
    flaky_fixtures_excluded: list[str]
    total_tokens_in: int
    total_tokens_out: int
    cost_estimate_usd: float
    pricing_rate_as_of: str
    error_count: int
    halt_due_to_flakiness: bool


def _records_by_fixture_variant(
    records: Iterable[RunRecord],
) -> dict[tuple[str, str], list[RunRecord]]:
    grouped: dict[tuple[str, str], list[RunRecord]] = {}
    for record in records:
        grouped.setdefault((record.fixture_id, record.variant), []).append(record)
    return grouped


def _tally_assertions(records: list[RunRecord]) -> _AssertionTally:
    """Sum passed and total assertion counts across all runs.

    A run with `outcome=error` contributes its full assertion count to the
    denominator and zero to the numerator. The flag `error_runs` lets the
    aggregator subtract the failed runs from the denominator when
    computing `recall_excluding_errors`.
    """
    passed = 0
    total = 0
    error_runs = 0
    for record in records:
        for assertion in record.assertions:
            total += 1
            if record.outcome == "success" and assertion.passed:
                passed += 1
        if record.outcome == "error":
            error_runs += 1
    return _AssertionTally(passed=passed, total=total, error_runs=error_runs)


def _per_run_pass_rate(record: RunRecord) -> float:
    """Pass rate across the assertions of one record. Errors count as 0.

    Used for per-fixture distribution (the runs.jsonl rows for one
    (fixture, variant) tuple) and for flakiness detection.
    """
    if record.outcome == "error" or not record.assertions:
        return 0.0
    passed = sum(1 for a in record.assertions if a.passed)
    return passed / len(record.assertions)


def _per_fixture_pass_rates(
    grouped: dict[tuple[str, str], list[RunRecord]],
) -> dict[str, dict[str, list[float]]]:
    """Build {fixture_id: {variant: [pass_rate_per_run, ...]}}."""
    out: dict[str, dict[str, list[float]]] = {}
    for (fixture_id, variant), runs in grouped.items():
        rates = [_per_run_pass_rate(r) for r in runs]
        out.setdefault(fixture_id, {})[variant] = rates
    return out


def _detect_flaky_fixtures(
    per_fixture: dict[str, dict[str, list[float]]],
) -> list[str]:
    """Fixtures with non-zero pass-rate variance across runs (any variant).

    Per REQ-004 AC-10: non-zero variance on any variant marks the fixture
    flaky. The contingency protocol decides whether to actually exclude it.
    """
    flaky: list[str] = []
    for fixture_id, variants in per_fixture.items():
        for runs in variants.values():
            if not runs:
                continue
            mean = sum(runs) / len(runs)
            variance = sum((r - mean) ** 2 for r in runs) / len(runs)
            if variance > 0:
                flaky.append(fixture_id)
                break
    return sorted(flaky)


def _recall_from_grouped(
    grouped: dict[tuple[str, str], list[RunRecord]],
    variant: str,
    *,
    fixture_ids: list[str],
    include_errors: bool = True,
) -> float:
    """Recall = sum(passed_assertions) / sum(total_assertions).

    `include_errors`: when False, the denominator excludes assertion counts
    from runs whose outcome is `error`. Numerator is unchanged because
    failed assertions are already 0 there.
    """
    passed = 0
    total = 0
    for fixture_id in fixture_ids:
        runs = grouped.get((fixture_id, variant), [])
        for record in runs:
            for assertion in record.assertions:
                if record.outcome == "error" and not include_errors:
                    continue
                total += 1
                if record.outcome == "success" and assertion.passed:
                    passed += 1
    if total == 0:
        return 0.0
    return passed / total


def _percentile(values: list[float], pct: float) -> float:
    """Linear interpolation percentile. Avoids pulling in numpy."""
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


def _paired_bootstrap_ci(
    grouped: dict[tuple[str, str], list[RunRecord]],
    fixture_ids: list[str],
    *,
    iterations: int = BOOTSTRAP_ITERATIONS,
    rng: random.Random | None = None,
) -> tuple[float, float]:
    """95% paired bootstrap CI on the signed recall delta.

    Resamples fixture ids with replacement; computes agent and baseline
    recall on the resample; takes the delta. Returns the [2.5, 97.5]
    percentile of the resampled deltas.
    """
    if not fixture_ids:
        return (0.0, 0.0)
    rng = rng or random.Random(42)
    n = len(fixture_ids)
    deltas: list[float] = []
    for _ in range(iterations):
        sample = [fixture_ids[rng.randrange(n)] for _ in range(n)]
        agent_recall = _recall_from_grouped(grouped, "agent", fixture_ids=sample)
        baseline_recall = _recall_from_grouped(
            grouped, "baseline", fixture_ids=sample
        )
        deltas.append(agent_recall - baseline_recall)
    return (
        _percentile(deltas, CI_LOWER_PERCENTILE),
        _percentile(deltas, CI_UPPER_PERCENTILE),
    )


def _cost_estimate(
    model_id: str, total_tokens_in: int, total_tokens_out: int
) -> float:
    rates = MODEL_PRICING_RATES_USD_PER_1K_TOKENS.get(model_id)
    if rates is None:
        return 0.0
    return (
        total_tokens_in * rates["input"] + total_tokens_out * rates["output"]
    ) / 1000.0


class ReportAggregator:
    """Build an AggregateResult from a list of RunRecord rows."""

    def __init__(
        self,
        records: list[RunRecord],
        *,
        model_id: str,
        bootstrap_iterations: int = BOOTSTRAP_ITERATIONS,
        rng: random.Random | None = None,
    ) -> None:
        self._records = records
        self._model_id = model_id
        self._iterations = bootstrap_iterations
        self._rng = rng or random.Random(42)

    def aggregate(self) -> AggregateResult:
        if not self._records:
            return _empty_result(self._model_id)
        grouped = _records_by_fixture_variant(self._records)
        per_fixture = _per_fixture_pass_rates(grouped)
        flaky_ids = _detect_flaky_fixtures(per_fixture)
        all_fixture_ids = sorted({fid for fid, _ in grouped.keys()})

        # Halt condition: > 30% of fixtures flaky → unstable methodology.
        halt = (
            len(all_fixture_ids) > 0
            and (len(flaky_ids) / len(all_fixture_ids)) > FLAKY_FIXTURE_HALT_FRACTION
        )

        # Stable subset for delta calculation. When ≤30% flaky, exclude them.
        excluded = list(flaky_ids) if not halt and flaky_ids else []
        stable_ids = [fid for fid in all_fixture_ids if fid not in set(excluded)]

        agent_recall = _recall_from_grouped(grouped, "agent", fixture_ids=stable_ids)
        baseline_recall = _recall_from_grouped(
            grouped, "baseline", fixture_ids=stable_ids
        )
        recall_delta = agent_recall - baseline_recall

        ci_low, ci_high = _paired_bootstrap_ci(
            grouped,
            fixture_ids=stable_ids,
            iterations=self._iterations,
            rng=self._rng,
        )

        # `recall_with_errors` keeps the full set; `recall_excluding_errors`
        # removes assertion rows from error-outcome runs from the denominator.
        # Both report on the agent variant; baseline error accounting matches.
        recall_with_errors = _recall_from_grouped(
            grouped, "agent", fixture_ids=all_fixture_ids, include_errors=True
        )
        recall_excluding_errors = _recall_from_grouped(
            grouped, "agent", fixture_ids=all_fixture_ids, include_errors=False
        )

        total_tokens_in = sum(r.tokens_in for r in self._records)
        total_tokens_out = sum(r.tokens_out for r in self._records)
        cost = _cost_estimate(self._model_id, total_tokens_in, total_tokens_out)
        error_count = sum(1 for r in self._records if r.outcome == "error")

        return AggregateResult(
            agent_recall=agent_recall,
            baseline_recall=baseline_recall,
            recall_delta=recall_delta,
            bootstrap_ci_95=(ci_low, ci_high),
            recall_with_errors=recall_with_errors,
            recall_excluding_errors=recall_excluding_errors,
            per_fixture_pass_rates=per_fixture,
            flakiness=bool(flaky_ids),
            flaky_fixtures_excluded=excluded,
            total_tokens_in=total_tokens_in,
            total_tokens_out=total_tokens_out,
            cost_estimate_usd=cost,
            pricing_rate_as_of=PRICING_RATE_AS_OF,
            error_count=error_count,
            halt_due_to_flakiness=halt,
        )


def _empty_result(model_id: str) -> AggregateResult:
    return AggregateResult(
        agent_recall=0.0,
        baseline_recall=0.0,
        recall_delta=0.0,
        bootstrap_ci_95=(0.0, 0.0),
        recall_with_errors=0.0,
        recall_excluding_errors=0.0,
        per_fixture_pass_rates={},
        flakiness=False,
        flaky_fixtures_excluded=[],
        total_tokens_in=0,
        total_tokens_out=0,
        cost_estimate_usd=0.0,
        pricing_rate_as_of=PRICING_RATE_AS_OF,
        error_count=0,
        halt_due_to_flakiness=False,
    )
