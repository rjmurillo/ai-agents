"""Canonical: scripts/github_core/rate_limit.py. Sync via scripts/sync_plugin_lib.py.

Extracted from ``scripts/github_core/api.py`` (Issue #1910) as a cohesive
module. ``api.py`` re-exports ``RateLimitResult``, ``DEFAULT_RATE_THRESHOLDS``,
and ``check_workflow_rate_limit`` so existing
``from .api import ...`` call sites stay valid.
"""

from __future__ import annotations

import json
import subprocess
import warnings
from dataclasses import dataclass

DEFAULT_RATE_THRESHOLDS: dict[str, int] = {
    "core": 100,
    "search": 15,
    "code_search": 5,
    "graphql": 100,
}


@dataclass
class RateLimitResult:
    """Structured result from rate limit check."""

    success: bool
    resources: dict[str, dict]
    summary_markdown: str
    core_remaining: int


def _fetch_rate_limit() -> dict:
    """Call ``gh api rate_limit`` and return the parsed JSON payload.

    Raises RuntimeError on transport failure or invalid JSON.
    """
    result = subprocess.run(
        ["gh", "api", "rate_limit"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to fetch rate limits: {result.stderr}")

    try:
        payload: dict = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Rate limit response was not valid JSON: {exc}") from exc
    return payload


def _evaluate_resource(
    resource: str,
    threshold: int,
    resource_data: dict | None,
) -> tuple[bool, dict | None, str]:
    """Evaluate one rate-limit resource against its threshold.

    Returns ``(passed, resource_entry, summary_row)``. A missing resource is a
    failure with a None entry and a MISSING row; the caller skips adding it to
    the resources map but still appends the row and marks the run failed.
    """
    if resource_data is None:
        warnings.warn(
            f"Resource '{resource}' not found in rate limit response",
            stacklevel=2,
        )
        return False, None, f"| {resource} | N/A | {threshold} | X MISSING |"

    remaining = resource_data["remaining"]
    limit = resource_data["limit"]
    reset = resource_data["reset"]
    passed = remaining >= threshold

    status = "OK" if passed else "TOO LOW"
    status_icon = "+" if passed else "X"

    entry = {
        "Remaining": remaining,
        "Limit": limit,
        "Reset": reset,
        "Threshold": threshold,
        "Passed": passed,
    }
    row = f"| {resource} | {remaining} | {threshold} | {status_icon} {status} |"
    return passed, entry, row


def check_workflow_rate_limit(
    resource_thresholds: dict[str, int] | None = None,
) -> RateLimitResult:
    """Check GitHub API rate limits before workflow execution.

    Args:
        resource_thresholds: Map of resource name to minimum remaining threshold.

    Returns:
        RateLimitResult with pass/fail per resource and markdown summary.
    """
    if resource_thresholds is None:
        resource_thresholds = dict(DEFAULT_RATE_THRESHOLDS)

    rate_limit = _fetch_rate_limit()

    resources: dict[str, dict] = {}
    all_passed = True
    summary_lines = [
        "### API Rate Limit Status",
        "",
        "| Resource | Remaining | Threshold | Status |",
        "|----------|-----------|-----------|--------|",
    ]

    for resource, threshold in resource_thresholds.items():
        resource_data = (rate_limit.get("resources") or {}).get(resource)
        passed, entry, row = _evaluate_resource(resource, threshold, resource_data)
        if not passed:
            all_passed = False
        if entry is not None:
            resources[resource] = entry
        summary_lines.append(row)

    return RateLimitResult(
        success=all_passed,
        resources=resources,
        summary_markdown="\n".join(summary_lines),
        core_remaining=((rate_limit.get("resources") or {}).get("core") or {}).get(
            "remaining", 0
        ),
    )
