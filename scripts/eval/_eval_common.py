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
