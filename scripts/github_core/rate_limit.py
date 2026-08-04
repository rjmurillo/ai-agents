"""GitHub API rate-limit checks.

Extracted from ``scripts/github_core/api.py`` (Issue #1910) as a cohesive
module. ``api.py`` re-exports ``RateLimitResult``, ``DEFAULT_RATE_THRESHOLDS``,
and ``check_workflow_rate_limit`` so existing
``from scripts.github_core.api import ...`` call sites stay valid.
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
    probe_error: str = ""


# GitHub refuses calls with "API rate limit exceeded" while ``gh api
# rate_limit`` still reports the matching bucket as nearly unused, because the
# rate_limit endpoint is exempt from the limit it reports. Reading only
# ``remaining`` therefore reports the API as healthy during a refusal that
# fails every real call (issue #4326). One non-exempt probe closes the gap.
#
# ``meta`` rather than ``user`` on purpose: it counts against core (so a
# refusal is observable) and it answers for every token type. ``GET /user``
# returns 403 "Resource not accessible by integration" for an Actions
# installation token, which would make this gate fail closed forever for any
# caller that is not using a PAT. Both current callers use a PAT; the next one
# might not.
_PROBE_ENDPOINT = "meta"

# REST and GraphQL carry separate quotas and refuse independently, so a REST
# probe alone reports the API healthy through a GraphQL-only refusal. That is
# the window issues #4344, #4333, and #4335 were all filed from, and it is the
# half of #4326 defect 2 a core-only probe cannot see. The GraphQL rung runs
# only when the caller asked about the graphql bucket, so a REST-only caller
# does not pay for a transport it will not use.
_GRAPHQL_PROBE_ARGS = ("api", "graphql", "-f", "query=query { viewer { login } }")


def _run_probe(args: tuple[str, ...]) -> str:
    """Run one non-exempt gh call and return its refusal text, else ""."""
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"probe call failed: {exc}"
    if result.returncode == 0:
        return ""
    return (result.stderr or result.stdout).strip() or "probe returned a non-zero exit"


def _probe_api_serving(probe_graphql: bool = True) -> str:
    """Return the first observed refusal across the probed transports, else "".

    The returned string is the observed failure, so a caller can report why the
    gate failed rather than pointing at healthy quota numbers.
    """
    rest_error = _run_probe(("api", _PROBE_ENDPOINT))
    if rest_error:
        return f"REST (`gh api {_PROBE_ENDPOINT}`): {rest_error}"
    if not probe_graphql:
        return ""
    graphql_error = _run_probe(_GRAPHQL_PROBE_ARGS)
    if graphql_error:
        return f"GraphQL (viewer): {graphql_error}"
    return ""


def _probe_failure_is_a_refusal(probe_error: str) -> bool:
    """True when the probe failure is a quota refusal, not an upstream wobble.

    The probe exists to catch the one condition the payload cannot show: GitHub
    refusing calls while the buckets read healthy (issue #4326 defect 2).
    Failing the gate on every nonzero probe would be the opposite defect, a 5xx
    or a dropped connection read as fatal, which is what issue #3139 is about.
    So only rate-limit wording closes the gate; a transport failure is reported
    and the work proceeds, exactly as it did before the probe existed.

    Imported inside the function on purpose: ``api`` imports this module, so a
    module-level import would be a cycle.
    """
    from scripts.github_core.api import GhAuthStatus, classify_gh_failure_text

    return classify_gh_failure_text(probe_error) in (
        GhAuthStatus.RATE_LIMITED,
        GhAuthStatus.SECONDARY_RATE_LIMITED,
    )


def _fetch_rate_limit() -> dict:
    """Call ``gh api rate_limit`` and return the parsed JSON payload.

    Raises RuntimeError on transport failure or invalid JSON.
    """
    result = subprocess.run(  # subprocess-encoding: strict-ok
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

    Reports ``success=True`` only when every threshold passes AND one live
    non-exempt call is actually served. Callers read this as "the API will serve
    requests" (``scripts/invoke_pr_maintenance.py``,
    ``.github/scripts/invoke_pr_maintenance.py``,
    ``scripts/update_reviewer_signal_stats.py``), and before issue #4326 the
    payload-only check reported healthy quota during refusals that failed every
    real call.

    Args:
        resource_thresholds: Map of resource name to minimum remaining threshold.

    Returns:
        RateLimitResult with pass/fail per resource, the probe outcome, and a
        markdown summary.
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

    probe_error = _probe_api_serving(probe_graphql="graphql" in resource_thresholds)
    if probe_error and _probe_failure_is_a_refusal(probe_error):
        all_passed = False
        summary_lines.append("| live probe | N/A | served | X REFUSED |")
        summary_lines.append("")
        summary_lines.append(f"Live probe was refused: {probe_error}")
    elif probe_error:
        summary_lines.append("| live probe | N/A | served | ! UNRESOLVED |")
        summary_lines.append("")
        summary_lines.append(
            f"Live probe did not complete: {probe_error}. "
            "Not a quota refusal, so the gate is not closed on it."
        )

    return RateLimitResult(
        success=all_passed,
        resources=resources,
        summary_markdown="\n".join(summary_lines),
        core_remaining=((rate_limit.get("resources") or {}).get("core") or {}).get(
            "remaining", 0
        ),
        probe_error=probe_error,
    )
