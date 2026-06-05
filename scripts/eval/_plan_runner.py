"""PlanRunner: cost + scope estimation. DESIGN-004 §5.3a.

Imports `MODEL_PRICING_RATES_USD_PER_1K_TOKENS` and `PRICING_RATE_AS_OF`
from `_eval_common.py`. T4-3's `_report_aggregator.py` imports the same
constants from the same owner.
"""

from __future__ import annotations

from _eval_agent_types import ExecutionPlan, Fixture
from _eval_common import (
    EST_TOKENS_PER_CALL,
    MODEL_PRICING_RATES_USD_PER_1K_TOKENS,
    PRICING_RATE_AS_OF,
)

# Default variants for the v1 spike (ADR-058): one agent prompt vs. one
# baseline prompt. Held in a tuple to make the structure obvious at the call
# site. The form-factor v2 spike (Issue #1875) opts into the third `skill`
# variant via FORM_FACTOR_VARIANTS; the default stays two-wide so the v1
# cost plan and its locked dry-run output do not move.
VARIANTS: tuple[str, ...] = ("agent", "baseline")
# Issue #1875: the v2 form-factor spike compares all three variants so the
# report can compute the agent-baseline, skill-baseline, and agent-skill
# pairwise CIs. Opt in with `--include-skill` on the runner.
FORM_FACTOR_VARIANTS: tuple[str, ...] = ("agent", "baseline", "skill")
SUPPORTED_VARIANTS = frozenset(FORM_FACTOR_VARIANTS)

# Token estimation: 70/30 input/output split. Reflects observed v1/v2 spike
# traces (input ~ system prompt + user message; output ~ short verdict +
# brief explanation, capped at 80 words by OUTPUT_SHAPE_SUFFIX). Refined
# when the live run produces measured numbers; for the dry-run preview,
# this heuristic is fine.
_INPUT_TOKEN_FRACTION = 0.7
_OUTPUT_TOKEN_FRACTION = 1.0 - _INPUT_TOKEN_FRACTION


class UnsupportedModelError(Exception):
    """Raised when build_plan is called with an unpriced model id."""


def _estimate_tokens(planned_calls: int) -> tuple[int, int]:
    total_tokens = planned_calls * EST_TOKENS_PER_CALL
    tokens_in = int(total_tokens * _INPUT_TOKEN_FRACTION)
    tokens_out = total_tokens - tokens_in
    return tokens_in, tokens_out


def _estimate_cost_usd(model_id: str, tokens_in: int, tokens_out: int) -> float:
    rates = MODEL_PRICING_RATES_USD_PER_1K_TOKENS.get(model_id)
    if rates is None:
        raise UnsupportedModelError(
            f"No pricing rate for model_id={model_id!r}. "
            f"Add it to MODEL_PRICING_RATES_USD_PER_1K_TOKENS in _eval_common.py."
        )
    return (tokens_in * rates["input"] + tokens_out * rates["output"]) / 1000.0


class PlanRunner:
    """Compute the planned execution scope and cost estimate."""

    @staticmethod
    def build_plan(
        fixtures: list[Fixture],
        model_id: str,
        n_runs: int = 3,
        variants: tuple[str, ...] = VARIANTS,
    ) -> ExecutionPlan:
        if not fixtures:
            raise ValueError("build_plan requires at least one fixture")
        if n_runs < 1:
            raise ValueError(f"n_runs must be >= 1, got {n_runs}")
        if not variants:
            raise ValueError("build_plan requires at least one variant")
        duplicate_variants = sorted(
            {variant for variant in variants if variants.count(variant) > 1}
        )
        if duplicate_variants:
            raise ValueError(f"duplicate variants are not allowed: {duplicate_variants}")
        unsupported_variants = sorted(set(variants) - SUPPORTED_VARIANTS)
        if unsupported_variants:
            raise ValueError(f"unsupported variant(s): {unsupported_variants}")

        planned_calls = len(fixtures) * len(variants) * n_runs
        tokens_in, tokens_out = _estimate_tokens(planned_calls)
        cost_usd = _estimate_cost_usd(model_id, tokens_in, tokens_out)

        return ExecutionPlan(
            fixtures=fixtures,
            variants=variants,  # type: ignore[arg-type]
            n_runs=n_runs,
            model_id=model_id,
            planned_calls=planned_calls,
            estimated_tokens_in=tokens_in,
            estimated_tokens_out=tokens_out,
            estimated_cost_usd=cost_usd,
            pricing_rate_as_of=PRICING_RATE_AS_OF,
        )

    @staticmethod
    def format_plan_lines(plan: ExecutionPlan) -> list[str]:
        """Lines printed by `--dry-run`. Format is locked by the test suite."""
        return [
            f"planned_calls={plan.planned_calls}",
            f"estimated_tokens_in={plan.estimated_tokens_in}",
            f"estimated_tokens_out={plan.estimated_tokens_out}",
            f"cost_estimate_usd={plan.estimated_cost_usd:.2f} "
            f"rate_as_of={plan.pricing_rate_as_of}",
        ]
