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
from _plan_runner import UnsupportedModelError

BOOTSTRAP_ITERATIONS = 10000
CI_LOWER_PERCENTILE = 2.5
CI_UPPER_PERCENTILE = 97.5
# ADR-058 §"halt-due-to-flakiness" outcome / REQ-004 AC-10: methodology
# halts when too many fixtures are marked flaky after the contingency
# rerun. The 0.30 fraction is normative at large N; do not adjust without
# an ADR amendment.
FLAKY_FIXTURE_HALT_FRACTION = 0.30
# Small-N floor for the halt count. At N=10 the strict "more than 30%"
# gate halts on 4 flaky fixtures, which is too tight: a couple of flaky
# fixtures should not invalidate a small corpus. The N-aware count below
# raises the floor so that small corpora tolerate more flakiness in
# absolute terms while the 30% gate still governs at large N. See ADR-058
# (N-aware halt threshold note) and Issue #1878.
FLAKY_HALT_SMALL_N_FLOOR = 5
# REQ-004 AC-10: a fixture is flaky when its pass rate disagrees on >=2 of
# 5 contingency reps for the same (prompt_sha, fixture_set_sha).
CONTINGENCY_PERSISTENT_THRESHOLD = 2


def _flaky_halt_count(fixture_count: int) -> int:
    """Minimum flaky-fixture count that halts the methodology.

    N-aware threshold: `max(floor(0.30 * N) + 1, min(5, N // 2))`. The
    first term is the strict "more than 30%" gate from REQ-004 AC-10 and
    ADR-058: a flaky share of exactly 30% does NOT halt, only a share
    strictly greater than 30% does. It governs at large N. The second
    term is a small-N floor that tolerates a couple of flaky fixtures in a
    tiny corpus. The methodology halts when the flaky count is greater
    than or equal to this value.

    The fraction term is computed with integer arithmetic so an exact 30%
    boundary is handled without float rounding (N=30 -> halt at 10, not 9;
    N=20 -> 7; N=10 -> 4, but the small-N floor of 5 wins there).

    Worked values: N=2 -> max(1, 1)=1; N=10 -> max(4, 5)=5 (so 4 flaky of
    10 does NOT halt); N=30 -> max(10, 5)=10 (the strict 30% gate wins).
    """
    if fixture_count <= 0:
        return 0
    halt_percent = round(FLAKY_FIXTURE_HALT_FRACTION * 100)
    # Smallest integer strictly greater than 30% of N ("more than 30%").
    fraction_term = (halt_percent * fixture_count) // 100 + 1
    floor_term = min(FLAKY_HALT_SMALL_N_FLOOR, fixture_count // 2)
    return max(fraction_term, floor_term)


class EmptyRunError(Exception):
    """Raised when `aggregate()` is called with zero records.

    A run that wrote no records cannot produce a meaningful report; the
    runner should exit `EXIT_LOGIC` rather than ship a success-shaped
    report full of zeros.
    """


@dataclass
class AggregateResult:
    """Output of ReportAggregator. Consumed by ReportWriter.

    `tokens_estimated` is True when any record contributed to the totals
    used a token-length heuristic instead of measured `usage` values.
    Downstream report rendering surfaces this caveat next to the cost
    estimate.
    """

    agent_recall: float
    baseline_recall: float
    recall_delta: float
    bootstrap_ci_95: tuple[float, float]
    recall_with_errors: float
    recall_excluding_errors: float
    per_fixture_pass_rates: dict[str, dict[str, list[float]]]
    flakiness: bool
    flaky_fixtures_detected: list[str]
    flaky_fixtures_excluded: list[str]
    total_tokens_in: int
    total_tokens_out: int
    cost_estimate_usd: float
    pricing_rate_as_of: str
    error_count: int
    halt_due_to_flakiness: bool
    tokens_estimated: bool = True
    # True when the flaky count reached the N-aware halt count. When the
    # aggregator runs in flag-and-continue mode, `halt_due_to_flakiness`
    # stays False but this flag records that the threshold was crossed, so
    # the caller can surface the warning without invalidating the run.
    flaky_halt_threshold_crossed: bool = False


def _records_by_fixture_variant(
    records: Iterable[RunRecord],
) -> dict[tuple[str, str], list[RunRecord]]:
    grouped: dict[tuple[str, str], list[RunRecord]] = {}
    for record in records:
        grouped.setdefault((record.fixture_id, record.variant), []).append(record)
    return grouped


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
    """Fixtures whose pass-rate disagreement exceeds the AC-10 threshold.

    Default n_runs=3 protocol: any non-zero variance marks the fixture
    flaky. That is the smallest reliable signal for three runs.

    Contingency-rerun protocol (n_runs=5): a fixture is flaky only when
    `CONTINGENCY_PERSISTENT_THRESHOLD` (2) or more runs disagree with the
    majority. A 1-of-5 failure is a transient blip and is NOT flaky.

    Mixed n_runs across variants: the strictest applicable rule wins per
    variant. Variants with five or more runs use the contingency rule;
    others use the variance rule.
    """
    flaky: list[str] = []
    for fixture_id, variants in per_fixture.items():
        for runs in variants.values():
            if not runs:
                continue
            if _variant_is_flaky(runs):
                flaky.append(fixture_id)
                break
    return sorted(flaky)


def _variant_is_flaky(runs: list[float]) -> bool:
    """Apply the appropriate flakiness rule for the given run series."""
    if len(runs) >= 5:
        # Pass-rate values are in [0, 1]; the "majority" is the value
        # carried by ≥3 of 5 runs. The minority count is the disagreement.
        rounded = [round(r, 6) for r in runs]
        counts: dict[float, int] = {}
        for value in rounded:
            counts[value] = counts.get(value, 0) + 1
        majority_count = max(counts.values())
        minority = len(rounded) - majority_count
        return minority >= CONTINGENCY_PERSISTENT_THRESHOLD
    mean = sum(runs) / len(runs)
    variance = sum((r - mean) ** 2 for r in runs) / len(runs)
    return variance > 0


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


def pairwise_bootstrap_ci(
    grouped: dict[tuple[str, str], list[RunRecord]],
    fixture_ids: list[str],
    variant_a: str,
    variant_b: str,
    *,
    iterations: int = BOOTSTRAP_ITERATIONS,
    rng: random.Random | None = None,
) -> tuple[float, float]:
    """95% paired bootstrap CI on the signed recall delta (variant_a - variant_b).

    Resamples fixture ids with replacement; computes recall for both variants
    on the resample; takes the delta. Returns the [2.5, 97.5] percentile of
    the resampled deltas. Generalizes the agent-vs-baseline CI to any variant
    pair so the form-factor v2 spike (Issue #1875) can compute the
    skill-baseline and agent-skill CIs from the same record set.
    """
    if not fixture_ids:
        return (0.0, 0.0)
    rng = rng or random.Random(42)
    n = len(fixture_ids)
    deltas: list[float] = []
    for _ in range(iterations):
        sample = [fixture_ids[rng.randrange(n)] for _ in range(n)]
        recall_a = _recall_from_grouped(grouped, variant_a, fixture_ids=sample)
        recall_b = _recall_from_grouped(grouped, variant_b, fixture_ids=sample)
        deltas.append(recall_a - recall_b)
    return (
        _percentile(deltas, CI_LOWER_PERCENTILE),
        _percentile(deltas, CI_UPPER_PERCENTILE),
    )


def _paired_bootstrap_ci(
    grouped: dict[tuple[str, str], list[RunRecord]],
    fixture_ids: list[str],
    *,
    iterations: int = BOOTSTRAP_ITERATIONS,
    rng: random.Random | None = None,
) -> tuple[float, float]:
    """95% paired bootstrap CI on the agent-vs-baseline recall delta.

    Thin wrapper over `pairwise_bootstrap_ci` for the v1 (ADR-058) headline
    metric. Kept so the existing aggregate path and its tests do not move.
    """
    return pairwise_bootstrap_ci(
        grouped,
        fixture_ids,
        "agent",
        "baseline",
        iterations=iterations,
        rng=rng,
    )


def _cost_estimate(
    model_id: str, total_tokens_in: int, total_tokens_out: int
) -> float:
    """Return USD cost for the given token totals. Raises on unpriced models.

    Returning 0.0 for an unpriced model would render a "free run" report
    that hides the missing price. The runner translates the raised
    `UnsupportedModelError` into exit code 2 (config) so operators can
    add the rate to `_eval_common.MODEL_PRICING_RATES_USD_PER_1K_TOKENS`.
    """
    rates = MODEL_PRICING_RATES_USD_PER_1K_TOKENS.get(model_id)
    if rates is None:
        raise UnsupportedModelError(
            f"No pricing rate for model_id={model_id!r}. "
            f"Add it to MODEL_PRICING_RATES_USD_PER_1K_TOKENS in _eval_common.py."
        )
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
        flag_only_on_flaky_halt: bool = False,
    ) -> None:
        self._records = records
        self._model_id = model_id
        self._iterations = bootstrap_iterations
        self._rng = rng or random.Random(42)
        # Flag-and-continue: when True, crossing the N-aware halt count does
        # not set `halt_due_to_flakiness`. The flaky fixtures are excluded
        # and the run continues, with `flaky_halt_threshold_crossed` set so
        # the caller can warn. Default False preserves the hard-halt
        # behavior the methodology assumes.
        self._flag_only_on_flaky_halt = flag_only_on_flaky_halt

    def aggregate(self) -> AggregateResult:
        if not self._records:
            raise EmptyRunError(
                "no records to aggregate; aggregate() requires at least one "
                "RunRecord. Common cause: every triple was skipped on resume "
                "with no new work performed."
            )
        grouped = _records_by_fixture_variant(self._records)
        per_fixture = _per_fixture_pass_rates(grouped)
        flaky_ids = _detect_flaky_fixtures(per_fixture)
        all_fixture_ids = sorted({fid for fid, _ in grouped.keys()})

        # Halt condition: flaky count reaches the N-aware halt count →
        # unstable methodology. The N-aware count raises the small-N floor
        # so a tiny corpus is not halted by a couple of flaky fixtures.
        fixture_count = len(all_fixture_ids)
        halt_count = _flaky_halt_count(fixture_count) if fixture_count > 0 else 0
        threshold_crossed = fixture_count > 0 and len(flaky_ids) >= halt_count
        # Flag-and-continue mode records the crossing but does not halt.
        halt = threshold_crossed and not self._flag_only_on_flaky_halt

        # Stable subset for delta calculation. When the run does not halt,
        # exclude the flaky fixtures and continue on the stable subset.
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

        # `recall_with_errors` uses the same stable subset as headline recall;
        # `recall_excluding_errors` removes assertion rows from error-outcome
        # runs from the denominator. Both report on the agent variant and use
        # the same fixture set as the headline metrics for comparability.
        recall_with_errors = _recall_from_grouped(
            grouped, "agent", fixture_ids=stable_ids, include_errors=True
        )
        recall_excluding_errors = _recall_from_grouped(
            grouped, "agent", fixture_ids=stable_ids, include_errors=False
        )

        total_tokens_in = sum(r.tokens_in for r in self._records)
        total_tokens_out = sum(r.tokens_out for r in self._records)
        cost = _cost_estimate(self._model_id, total_tokens_in, total_tokens_out)
        error_count = sum(1 for r in self._records if r.outcome == "error")
        # Cost is only authoritative when every contributing record carries
        # measured token usage. Any estimated record taints the total.
        tokens_estimated = any(
            getattr(r, "tokens_estimated", True) for r in self._records
        )

        return AggregateResult(
            agent_recall=agent_recall,
            baseline_recall=baseline_recall,
            recall_delta=recall_delta,
            bootstrap_ci_95=(ci_low, ci_high),
            recall_with_errors=recall_with_errors,
            recall_excluding_errors=recall_excluding_errors,
            per_fixture_pass_rates=per_fixture,
            flakiness=bool(flaky_ids),
            flaky_fixtures_detected=list(flaky_ids),
            flaky_fixtures_excluded=excluded,
            total_tokens_in=total_tokens_in,
            total_tokens_out=total_tokens_out,
            cost_estimate_usd=cost,
            pricing_rate_as_of=PRICING_RATE_AS_OF,
            error_count=error_count,
            halt_due_to_flakiness=halt,
            tokens_estimated=tokens_estimated,
            flaky_halt_threshold_crossed=threshold_crossed,
        )


# ---------------------------------------------------------------------------
# Form-factor comparison (Issue #1875, follow-on to ADR-058).
#
# The v1 aggregator answers "does the agent's specialization beat the naive
# baseline?" (agent - baseline). The form-factor v2 spike adds the `skill`
# variant and asks two more questions from the SAME record set:
#   - skill - baseline: did the content help at all, regardless of form?
#   - agent - skill:     did the agent FORM add value beyond the content?
# The verdict picks the cheaper form when the form does not measurably help.
# ---------------------------------------------------------------------------

FormFactorVerdict = str  # {"prefer-skill-form", "prefer-agent-form", "inconclusive"}


@dataclass
class FormFactorComparison:
    """Three pairwise recall deltas + CIs and a form-factor verdict.

    `agent_skill_ci` is the load-bearing interval: its relation to zero
    decides the verdict. `skill_tokens` and `agent_tokens` carry the
    per-variant token totals so the cost-vs-recall trade-off (REQ from Issue
    #1875 AC: "cost tracking distinguishes per-variant token usage") is
    visible to the report consumer.
    """

    agent_recall: float
    baseline_recall: float
    skill_recall: float
    agent_baseline_delta: float
    skill_baseline_delta: float
    agent_skill_delta: float
    agent_baseline_ci: tuple[float, float]
    skill_baseline_ci: tuple[float, float]
    agent_skill_ci: tuple[float, float]
    agent_tokens_in: int
    agent_tokens_out: int
    skill_tokens_in: int
    skill_tokens_out: int
    verdict: FormFactorVerdict
    schema_version: int = 1


def _tokens_for_variant(
    records: list[RunRecord], variant: str
) -> tuple[int, int]:
    """Sum (tokens_in, tokens_out) across every record for one variant."""
    tokens_in = sum(r.tokens_in for r in records if r.variant == variant)
    tokens_out = sum(r.tokens_out for r in records if r.variant == variant)
    return tokens_in, tokens_out


def _form_factor_verdict(
    agent_skill_delta: float,
    agent_skill_ci: tuple[float, float],
    skill_tokens_total: int,
    agent_tokens_total: int,
) -> FormFactorVerdict:
    """Map the agent-skill delta, its CI, and per-variant cost to a verdict.

    Criteria mirror the Issue #1875 normative table:
      - prefer-agent-form: delta > 0 AND CI lower bound > 0 (the agent form
        genuinely helps beyond the content).
      - prefer-skill-form: the CI spans zero (form does not measurably help)
        AND the skill variant is cheaper. Default to the cheaper form.
      - inconclusive: the CI spans zero but the skill is not cheaper, so
        there is no cost reason to prefer either form.
    The order matters: a genuine agent-form win wins even when skill is
    cheaper.
    """
    ci_low, ci_high = agent_skill_ci
    if agent_skill_delta > 0 and ci_low > 0:
        return "prefer-agent-form"
    ci_spans_zero = ci_low <= 0 <= ci_high
    if ci_spans_zero and skill_tokens_total < agent_tokens_total:
        return "prefer-skill-form"
    return "inconclusive"


def compute_form_factor(
    records: list[RunRecord],
    *,
    iterations: int = BOOTSTRAP_ITERATIONS,
    rng: random.Random | None = None,
) -> FormFactorComparison:
    """Compute the three pairwise CIs and the form-factor verdict.

    Requires records for all three variants (agent, baseline, skill). Raises
    EmptyRunError on an empty record set and ValueError when the skill
    variant is absent (the comparison is meaningless without it).
    """
    if not records:
        raise EmptyRunError("compute_form_factor requires at least one record")
    grouped = _records_by_fixture_variant(records)
    present = {variant for _, variant in grouped.keys()}
    missing = {"agent", "baseline", "skill"} - present
    if missing:
        raise ValueError(
            f"form-factor comparison needs agent, baseline, and skill "
            f"variants; missing: {sorted(missing)}"
        )
    fixture_ids = sorted({fid for fid, _ in grouped.keys()})

    agent_recall = _recall_from_grouped(grouped, "agent", fixture_ids=fixture_ids)
    baseline_recall = _recall_from_grouped(
        grouped, "baseline", fixture_ids=fixture_ids
    )
    skill_recall = _recall_from_grouped(grouped, "skill", fixture_ids=fixture_ids)

    rng = rng or random.Random(42)
    agent_baseline_ci = pairwise_bootstrap_ci(
        grouped, fixture_ids, "agent", "baseline", iterations=iterations, rng=rng
    )
    skill_baseline_ci = pairwise_bootstrap_ci(
        grouped, fixture_ids, "skill", "baseline", iterations=iterations, rng=rng
    )
    agent_skill_ci = pairwise_bootstrap_ci(
        grouped, fixture_ids, "agent", "skill", iterations=iterations, rng=rng
    )

    agent_tokens_in, agent_tokens_out = _tokens_for_variant(records, "agent")
    skill_tokens_in, skill_tokens_out = _tokens_for_variant(records, "skill")

    verdict = _form_factor_verdict(
        agent_recall - skill_recall,
        agent_skill_ci,
        skill_tokens_in + skill_tokens_out,
        agent_tokens_in + agent_tokens_out,
    )

    return FormFactorComparison(
        agent_recall=agent_recall,
        baseline_recall=baseline_recall,
        skill_recall=skill_recall,
        agent_baseline_delta=agent_recall - baseline_recall,
        skill_baseline_delta=skill_recall - baseline_recall,
        agent_skill_delta=agent_recall - skill_recall,
        agent_baseline_ci=agent_baseline_ci,
        skill_baseline_ci=skill_baseline_ci,
        agent_skill_ci=agent_skill_ci,
        agent_tokens_in=agent_tokens_in,
        agent_tokens_out=agent_tokens_out,
        skill_tokens_in=skill_tokens_in,
        skill_tokens_out=skill_tokens_out,
        verdict=verdict,
    )


