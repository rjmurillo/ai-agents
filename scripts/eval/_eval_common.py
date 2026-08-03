"""Shared utilities for eval scripts.

Extracted from eval-agents.py and eval-knowledge-integration.py to eliminate
duplication of score aggregation logic.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EST_TOKENS_PER_CALL = 3500  # ~2000-5000 tokens per call, use midpoint
FLAKINESS_VARIANCE_THRESHOLD = 1.0

# Pricing rates per 1K tokens, USD. Owner of these constants for both
# _plan_runner.py (T4-1) and _report_aggregator.py (T4-3) per DESIGN-004 §5.3a.
# When updating, also update PRICING_RATE_AS_OF.
MODEL_PRICING_RATES_USD_PER_1K_TOKENS: dict[str, dict[str, float]] = {
    # Legacy id retained for historical run cost lookups only; it is a dead
    # id (HTTP 404) and MUST NOT be used as a default (issue #2858).
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    # Verified rates from platform.claude.com/docs/en/about-claude/pricing
    # (retrieved 2026-08-01, every row below re-read from that table on that
    # date). Rates are per-1K tokens = base MTok rate / 1000. Sonnet 4.6:
    # $3/$15 per MTok. Opus 5, 4.6, and 4.8: $5/$25 per MTok. Haiku 4.5:
    # $1/$5 per MTok. These are the live pins enumerated in issue #2840, plus
    # claude-opus-5, which scripts/eval/panels/owner-copilot-cli.json
    # dispatches and which had no rate until issue #3905.
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    "claude-opus-4-6": {"input": 0.005, "output": 0.025},
    "claude-opus-4-8": {"input": 0.005, "output": 0.025},
    "claude-opus-5": {"input": 0.005, "output": 0.025},
    "claude-haiku-4-5": {"input": 0.001, "output": 0.005},
    # No row for gpt-5.6-sol on purpose (issue #3905). That id is reachable
    # only through the copilot-cli provider, which meters premium requests
    # rather than tokens, so no published per-token rate exists. A made-up
    # number here would put a fabricated figure in an operator cost report,
    # which is the failure issue #3786 records. Its cost basis is tracked in
    # PR #4005.
}
PRICING_RATE_AS_OF = "2026-08-01"

# Providers that bill by quota or premium-request rather than per token.
# For these providers no USD estimate is meaningful or available, so the
# plan runner skips the dollar-gate and prints a request-count summary instead.
QUOTA_BILLED_PROVIDERS = frozenset({"github", "github-models", "copilot", "copilot-cli"})


def cost_basis(provider: str | None = None) -> str:
    """Return "quota" for quota-billed providers, "usd" for token-billed ones.

    Resolves provider the same way _providers.resolve_provider does, so the
    plan cost and the actual transport always agree.
    """
    import os  # local import: only needed here, avoids module-level side effect

    resolved = (provider or os.environ.get("EVAL_PROVIDER") or "anthropic").strip().lower()
    return "requests" if resolved in QUOTA_BILLED_PROVIDERS else "usd"


def aggregate_multi_run_scores(
    run_scores: list[dict[str, Any]],
    dimensions: list[str],
) -> dict[str, Any]:
    """Aggregate scores across multiple runs per ADR-057 flakiness protocol.

    Returns averaged scores plus flakiness metadata (pass rate, variance).

    Args:
        run_scores: List of score dicts from individual runs.
        dimensions: List of dimension keys to aggregate (e.g. ["accuracy", "depth", "specificity"]).
    """
    if len(run_scores) == 1:
        return run_scores[0]

    aggregated: dict[str, Any] = {}
    for dim in dimensions:
        values = [s[dim] for s in run_scores if dim in s and s[dim] is not None]
        if values:
            aggregated[dim] = round(sum(values) / len(values), 2)
            aggregated[f"{dim}_variance"] = round(
                sum((v - aggregated[dim]) ** 2 for v in values) / len(values), 2
            )
        else:
            aggregated[dim] = 0.0

    # Flakiness detection: a scenario is flaky if any dimension varies by > threshold
    max_variance = max((aggregated.get(f"{d}_variance", 0) for d in dimensions), default=0)
    aggregated["runs"] = len(run_scores)
    aggregated["flaky"] = max_variance > FLAKINESS_VARIANCE_THRESHOLD
    aggregated["max_variance"] = round(max_variance, 2)

    # Preserve non-score fields from first run
    preserved_keys = ("complexity", "model_used", "reasoning")
    for key in preserved_keys:
        if key in run_scores[0]:
            aggregated[key] = run_scores[0][key]

    if len(run_scores) > 1:
        aggregated["per_run_detail"] = run_scores
    return aggregated
