"""GitHub API rate-limit checks.

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
        encoding="utf-8",
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

    Compares remaining quota for each resource against its threshold. Returns
    success=True when all resources are above threshold.

    KNOWN BLIND SPOT (issue #4326): GitHub's secondary/burst limiter produces
    HTTP 403 with rate-limit wording while primary quota remains healthy. The
    ``rate_limit`` endpoint does not expose this limiter, so this function can
    return success=True while individual API calls are being refused. Callers
    should not treat success=True as a guarantee that the API will serve
    requests; treat it as "primary quota is sufficient, proceed with backoff
    on 403 responses." Use ``probe_api_reachability`` when a live reachability
    check is required.

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


def probe_api_reachability(owner: str, repo: str) -> bool:
    """Make a cheap real REST call to detect burst-limiter 403 refusals.

    ``check_workflow_rate_limit`` cannot detect GitHub's secondary/burst
    limiter because that limiter does not appear in the ``rate_limit``
    payload (issue #4326). This function makes a single lightweight call
    (``GET /repos/{owner}/{repo}``) that is subject to the same limiter,
    returning False when the call is refused with a 403.

    Use before starting a workflow that will make many calls. A False return
    with healthy primary quota indicates a burst window; back off 60 to 90
    seconds and retry rather than resetting the reset timestamp.

    Returns:
        True when the API is reachable, False on any failure (403, timeout,
        transport error).
    """
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}", "--jq", ".full_name"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0
