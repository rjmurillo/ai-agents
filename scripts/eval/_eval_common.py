"""Shared utilities for eval scripts.

Extracted from eval-agents.py and eval-knowledge-integration.py to eliminate
duplication of score aggregation logic.
"""

from __future__ import annotations

import os
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
    # (retrieved 2026-07-08). Rates are per-1K tokens = base MTok rate / 1000.
    # Sonnet 4.6: $3/$15 per MTok. Opus 4.6 and 4.8: $5/$25 per MTok. Haiku
    # 4.5: $1/$5 per MTok. These are the live pins enumerated in issue #2840.
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    "claude-opus-4-6": {"input": 0.005, "output": 0.025},
    "claude-opus-4-8": {"input": 0.005, "output": 0.025},
    "claude-haiku-4-5": {"input": 0.001, "output": 0.005},
}
PRICING_RATE_AS_OF = "2026-07-08"

# Providers that meter requests against an account allowance instead of
# charging a published per-token USD rate. GitHub Models bills this way, so a
# dollar figure for a run routed through it is a number nobody publishes.
# Naming these providers lets the plan report the request count it will spend
# and leave the USD figure empty, rather than either inventing a third-party
# price or refusing to run a provider the transport already supports.
# Spellings match the aliases in `_providers._REGISTRY`.
QUOTA_BILLED_PROVIDERS: frozenset[str] = frozenset({"github", "github-models"})


def cost_basis(provider: str | None) -> str:
    """Return how *provider* bills: ``"usd"`` per token or ``"requests"``.

    The biller is the provider, not the model. The same model id served
    through GitHub Models is metered against a request allowance, and served
    through a per-token vendor is metered in dollars, so the basis has to
    follow the transport that will actually be charged.

    *provider* is resolved exactly as ``_providers.resolve_provider`` resolves
    it, ``(name or EVAL_PROVIDER or "anthropic").strip().lower()``, because the
    transport that resolution selects is the one that gets billed. Resolving
    any other way lets the two disagree: selecting GitHub Models through the
    environment alone, or spelling it ``GitHub-Models``, would route to a
    request-metered transport while this function still answered ``"usd"``,
    so the plan would promise dollars for a run that spends request quota.

    An unrecognized or absent provider answers ``"usd"``. That keeps the
    default Anthropic path, and any per-token vendor added later, on the
    existing rule: a missing rate is a real gap an operator must fill, not a
    licence to print a price.
    """
    selected = (provider or os.environ.get("EVAL_PROVIDER") or "anthropic").strip().lower()
    return "requests" if selected in QUOTA_BILLED_PROVIDERS else "usd"


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
    max_variance = max(
        (aggregated.get(f"{d}_variance", 0) for d in dimensions), default=0
    )
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
