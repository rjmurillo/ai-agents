#!/usr/bin/env python3
"""Measure workflow run coalescing effectiveness by analyzing GitHub Actions runs.

Queries GitHub Actions API to collect workflow run data, detects overlapping runs
within the same concurrency group, and calculates metrics for coalescing effectiveness,
race conditions, and cancellation performance.

Exit codes (ADR-035):
    0 - Success: Analysis completed
    1 - Error: Failed to fetch workflow data or process results
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, workspace)

from scripts.github_core.api import resolve_repo_params  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_WORKFLOWS: list[str] = [
    "ai-pr-quality-gate",
    "ai-spec-validation",
    "ai-session-protocol",
    "pr-validation",
    "label-pr",
    "memory-validation",
    "auto-assign-reviewer",
    "codeql-analysis",
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class WorkflowRun:
    """A single GitHub Actions workflow run."""

    id: int
    name: str
    created_at: str
    updated_at: str
    conclusion: str | None
    event: str
    head_branch: str
    pull_requests: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> WorkflowRun:
        """Create a WorkflowRun from GitHub API response data."""
        return cls(
            id=data.get("id", 0),
            name=data.get("name", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            conclusion=data.get("conclusion"),
            event=data.get("event", ""),
            head_branch=data.get("head_branch", ""),
            pull_requests=data.get("pull_requests") or [],
        )

    @property
    def created_dt(self) -> datetime:
        return _parse_datetime(self.created_at)

    @property
    def updated_dt(self) -> datetime:
        return _parse_datetime(self.updated_at)


@dataclass
class RunOverlap:
    """An overlap between two workflow runs."""

    concurrency_group: str
    run1: WorkflowRun
    run2: WorkflowRun
    run1_cancelled: bool
    run2_cancelled: bool
    is_race_condition: bool


@dataclass
class CoalescingMetrics:
    """Calculated coalescing effectiveness metrics."""

    total_runs: int
    cancelled_runs: int
    race_conditions: int
    successful_coalescing: int
    coalescing_effectiveness: float
    race_condition_rate: float
    avg_cancellation_time: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_datetime(iso_str: str) -> datetime:
    """Parse ISO 8601 datetime string to timezone-aware datetime."""
    cleaned = iso_str.replace("Z", "+00:00")
    return datetime.fromisoformat(cleaned)


# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------


def test_prerequisites() -> None:
    """Validate that gh CLI is installed and authenticated.

    Raises:
        RuntimeError: If gh CLI is missing or not authenticated.
    """
    try:
        subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("GitHub CLI (gh) is not installed or not in PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("GitHub CLI (gh) is not installed or not in PATH") from exc

    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError("GitHub CLI is not authenticated. Run: gh auth login")

    logger.debug("Prerequisites validated: gh CLI available and authenticated")


# ---------------------------------------------------------------------------
# Repository context
# ---------------------------------------------------------------------------


def get_repository_context(repository: str) -> dict[str, str]:
    """Get repository owner and name from parameter or git remote.

    Args:
        repository: Repository in owner/repo format, or empty string for auto-detect.

    Returns:
        Dict with 'Owner' and 'Repo' keys.

    Raises:
        RuntimeError: If repository format is invalid.
        SystemExit: If resolve_repo_params cannot determine the repo.
    """
    if repository:
        parts = repository.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise RuntimeError("Repository must be in format 'owner/repo'")
        return resolve_repo_params(parts[0], parts[1])

    return resolve_repo_params()


# ---------------------------------------------------------------------------
# Workflow run queries
# ---------------------------------------------------------------------------


def get_workflow_runs(
    owner: str,
    repo: str,
    start_date: datetime,
    workflow_names: list[str],
) -> list[WorkflowRun]:
    """Query GitHub Actions API for workflow runs within the date range.

    Args:
        owner: Repository owner.
        repo: Repository name.
        start_date: Only include runs created on or after this datetime.
        workflow_names: Workflow names to filter by (substring match).

    Returns:
        List of WorkflowRun objects matching criteria.
    """
    logger.info("Querying workflow runs since %s", start_date.isoformat())

    all_runs: list[WorkflowRun] = []
    page = 1
    per_page = 100
    continue_loop = True

    while continue_loop:
        api_url = f"/repos/{owner}/{repo}/actions/runs?page={page}&per_page={per_page}"
        logger.debug("Fetching page %d from API: %s", page, api_url)

        result = subprocess.run(
            ["gh", "api", api_url, "--jq", ".workflow_runs"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.warning("API request failed: %s", result.stderr.strip())
            break

        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning("Failed to parse API response")
            break

        if not response:
            break

        # Filter by workflow name (substring match)
        filtered = [
            r for r in response
            if any(wn in r.get("name", "") for wn in workflow_names)
        ]

        for run_data in filtered:
            run = WorkflowRun.from_api(run_data)
            if run.created_dt < start_date:
                continue_loop = False
                break
            all_runs.append(run)

        if len(response) < per_page:
            break

        page += 1

    logger.info("Retrieved %d workflow runs", len(all_runs))
    return all_runs


# ---------------------------------------------------------------------------
# Concurrency group extraction
# ---------------------------------------------------------------------------


def get_concurrency_group(run: WorkflowRun) -> str:
    """Extract concurrency group identifier from a workflow run.

    PR-triggered runs use a prefix based on workflow name plus PR number.
    Non-PR runs fall back to workflow name plus branch.
    """
    pr_number: int | None = None
    if run.event == "pull_request" and run.pull_requests:
        pr_number = run.pull_requests[0].get("number")

    if pr_number is not None:
        name = run.name
        if "quality" in name:
            prefix = "ai-quality"
        elif "spec" in name:
            prefix = "spec-validation"
        elif "session" in name:
            prefix = "session-protocol"
        elif "label" in name:
            prefix = "label-pr"
        elif "memory" in name:
            prefix = "memory-validation"
        elif "assign" in name:
            prefix = "auto-assign"
        else:
            prefix = "pr-validation"
        return f"{prefix}-{pr_number}"

    return f"{run.name}-{run.head_branch}"


# ---------------------------------------------------------------------------
# Overlap detection
# ---------------------------------------------------------------------------


def check_runs_overlap(run1: WorkflowRun, run2: WorkflowRun) -> bool:
    """Check if two workflow runs overlap in time.

    Run2 must start at or after Run1's start and before Run1's end.
    """
    run1_start = run1.created_dt
    run1_end = run1.updated_dt
    run2_start = run2.created_dt

    return run2_start < run1_end and run2_start >= run1_start


def get_overlapping_runs(runs: list[WorkflowRun]) -> list[RunOverlap]:
    """Find overlapping runs within concurrency groups.

    Groups runs by concurrency group, then checks each pair for overlap.
    """
    logger.info("Analyzing %d runs for overlaps", len(runs))

    # Group runs by concurrency group
    groups: dict[str, list[WorkflowRun]] = {}
    for run in runs:
        group_name = get_concurrency_group(run)
        groups.setdefault(group_name, []).append(run)

    overlaps: list[RunOverlap] = []

    for group_name, group_runs in groups.items():
        sorted_runs = sorted(group_runs, key=lambda r: r.created_at)

        for i in range(len(sorted_runs) - 1):
            for j in range(i + 1, len(sorted_runs)):
                r1 = sorted_runs[i]
                r2 = sorted_runs[j]

                if check_runs_overlap(r1, r2):
                    overlap = RunOverlap(
                        concurrency_group=group_name,
                        run1=r1,
                        run2=r2,
                        run1_cancelled=r1.conclusion == "cancelled",
                        run2_cancelled=r2.conclusion == "cancelled",
                        is_race_condition=(
                            r1.conclusion != "cancelled"
                            and r2.conclusion != "cancelled"
                        ),
                    )
                    overlaps.append(overlap)
                    logger.debug(
                        "Overlap detected in %s: Run %d vs %d",
                        group_name,
                        r1.id,
                        r2.id,
                    )

    logger.info("Found %d overlapping run pairs", len(overlaps))
    return overlaps


# ---------------------------------------------------------------------------
# Metrics calculation
# ---------------------------------------------------------------------------


def get_coalescing_metrics(
    runs: list[WorkflowRun],
    overlaps: list[RunOverlap],
) -> CoalescingMetrics:
    """Calculate coalescing effectiveness metrics from runs and overlaps."""
    total_runs = len(runs)
    cancelled_runs = sum(1 for r in runs if r.conclusion == "cancelled")

    # Deduplicate cancelled run IDs to avoid double-counting
    unique_cancelled_ids: set[int] = set()
    race_condition_count = 0

    for overlap in overlaps:
        if overlap.run1_cancelled:
            unique_cancelled_ids.add(overlap.run1.id)
        if overlap.is_race_condition:
            race_condition_count += 1

    successful_coalescing = len(unique_cancelled_ids)

    denominator = successful_coalescing + race_condition_count
    coalescing_effectiveness = (
        (successful_coalescing / denominator) * 100.0 if denominator > 0 else 0.0
    )

    race_condition_rate = (
        (race_condition_count / total_runs) * 100.0 if total_runs > 0 else 0.0
    )

    # Average cancellation time
    cancelled_overlaps = [o for o in overlaps if o.run1_cancelled]
    if cancelled_overlaps:
        times = [
            (o.run1.updated_dt - o.run1.created_dt).total_seconds()
            for o in cancelled_overlaps
        ]
        avg_cancellation_time = sum(times) / len(times)
    else:
        avg_cancellation_time = 0.0

    return CoalescingMetrics(
        total_runs=total_runs,
        cancelled_runs=cancelled_runs,
        race_conditions=race_condition_count,
        successful_coalescing=successful_coalescing,
        coalescing_effectiveness=round(coalescing_effectiveness, 2),
        race_condition_rate=round(race_condition_rate, 2),
        avg_cancellation_time=round(avg_cancellation_time, 2),
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def format_markdown_report(
    metrics: CoalescingMetrics,
    runs: list[WorkflowRun],
    overlaps: list[RunOverlap],
    start_date: datetime,
    end_date: datetime,
    workflows: list[str],
) -> str:
    """Generate markdown report from metrics data."""
    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    effectiveness_status = (
        "[On Track]" if metrics.coalescing_effectiveness >= 90 else "[Behind]"
    )
    race_status = "[On Track]" if metrics.race_condition_rate <= 10 else "[Behind]"
    cancel_status = (
        "[On Track]" if metrics.avg_cancellation_time <= 5 else "[Behind]"
    )

    lines: list[str] = [
        "# Workflow Run Coalescing Metrics",
        "",
        "## Report Period",
        "",
        f"- **From**: {start_str}",
        f"- **To**: {end_str}",
        f"- **Generated**: {now_utc} UTC",
        "",
        "## Executive Summary",
        "",
        "| Metric | Value | Target | Status |",
        "|--------|-------|--------|--------|",
        f"| Coalescing Effectiveness | {metrics.coalescing_effectiveness}% "
        f"| 90% | {effectiveness_status} |",
        f"| Race Condition Rate | {metrics.race_condition_rate}% "
        f"| <10% | {race_status} |",
        f"| Average Cancellation Time | {metrics.avg_cancellation_time} seconds "
        f"| <5s | {cancel_status} |",
        "",
        "## Workflow Run Analysis",
        "",
        "### Total Runs Summary",
        "",
        f"- **Total Workflow Runs**: {metrics.total_runs}",
        f"- **Cancelled Runs**: {metrics.cancelled_runs}",
        f"- **Successful Coalescing Events**: {metrics.successful_coalescing}",
        f"- **Race Conditions Detected**: {metrics.race_conditions}",
        "",
        "### Runs by Workflow",
        "",
        "| Workflow | Total Runs | Cancelled | Percentage |",
        "|----------|------------|-----------|------------|",
    ]

    # Group runs by workflow name
    workflow_groups: dict[str, list[WorkflowRun]] = {}
    for run in runs:
        workflow_groups.setdefault(run.name, []).append(run)

    for wf_name in sorted(workflow_groups, key=lambda n: len(workflow_groups[n]), reverse=True):
        group = workflow_groups[wf_name]
        total = len(group)
        cancelled = sum(1 for r in group if r.conclusion == "cancelled")
        pct = round((cancelled / total) * 100.0, 1) if total > 0 else 0.0
        lines.append(f"| {wf_name} | {total} | {cancelled} | {pct}% |")

    lines.extend([
        "",
        "### Concurrency Group Analysis",
        "",
        "| Concurrency Group | Total Runs | Overlaps Detected |",
        "|-------------------|------------|-------------------|",
    ])

    # Group runs by concurrency group
    cg_groups: dict[str, list[WorkflowRun]] = {}
    for run in runs:
        cg = get_concurrency_group(run)
        cg_groups.setdefault(cg, []).append(run)

    top_cgs = sorted(cg_groups.items(), key=lambda item: len(item[1]), reverse=True)[:10]
    for cg_name, cg_runs in top_cgs:
        group_overlaps = sum(1 for o in overlaps if o.concurrency_group == cg_name)
        lines.append(f"| {cg_name} | {len(cg_runs)} | {group_overlaps} |")

    if metrics.race_conditions > 0:
        lines.extend([
            "",
            "",
            "## Race Condition Details",
            "",
            "### Detected Race Conditions",
            "",
            "| Concurrency Group | Run 1 ID | Run 2 ID | Both Completed |",
            "|-------------------|----------|----------|----------------|",
        ])

        race_overlaps = [o for o in overlaps if o.is_race_condition][:10]
        for rc in race_overlaps:
            lines.append(
                f"| {rc.concurrency_group} | {rc.run1.id} | {rc.run2.id} | Yes |"
            )

    lines.extend(["", "", "## Recommendations", ""])

    if metrics.race_condition_rate > 10:
        lines.append(
            f"- **HIGH PRIORITY**: Race condition rate ({metrics.race_condition_rate}%) "
            "exceeds 10% threshold. Investigate trigger patterns and consider "
            "implementing debouncing."
        )
        lines.append(
            "- **MITIGATION**: Consider enabling debouncing for affected workflows "
            "using enable_debouncing=true in workflow_dispatch. This adds 10s latency "
            "but reduces race condition probability."
        )

    if metrics.avg_cancellation_time > 5:
        lines.append(
            f"- **MEDIUM PRIORITY**: Average cancellation time "
            f"({metrics.avg_cancellation_time}s) exceeds 5s target. "
            "Review workflow startup time and GitHub Actions infrastructure."
        )

    if 0 < metrics.coalescing_effectiveness < 90:
        lines.append(
            f"- **MEDIUM PRIORITY**: Coalescing effectiveness "
            f"({metrics.coalescing_effectiveness}%) is below 90% target. "
            "Review concurrency group configurations."
        )

    if metrics.coalescing_effectiveness >= 90 and metrics.race_condition_rate <= 10:
        lines.append(
            "- **STATUS**: All metrics are within target thresholds. Continue monitoring."
        )

    lines.extend([
        "",
        "## Data Sources",
        "",
        "- **GitHub Actions API**: `/repos/{owner}/{repo}/actions/runs`",
        f"- **Collection Period**: {start_str} to {end_str}",
        f"- **Workflows Analyzed**: {', '.join(workflows)}",
        "",
        "---",
        "",
        "*Generated by measure_workflow_coalescing.py*",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure workflow run coalescing effectiveness."
    )
    parser.add_argument(
        "--since",
        type=int,
        default=30,
        help="Number of days to analyze (default: 30)",
    )
    parser.add_argument(
        "--repository",
        default="",
        help="Repository in owner/repo format (inferred from git remote if omitted)",
    )
    parser.add_argument(
        "--workflows",
        action="append",
        default=None,
        help="Workflow names to analyze (repeatable, defaults to all AI workflows)",
    )
    parser.add_argument(
        "--output",
        choices=["json", "markdown", "summary"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output-path",
        default=".agents/metrics/workflow-coalescing.md",
        help="Path to save report (default: .agents/metrics/workflow-coalescing.md)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )

    workflows = args.workflows if args.workflows else list(DEFAULT_WORKFLOWS)

    try:
        test_prerequisites()

        repo_context = get_repository_context(args.repository)
        owner = repo_context["Owner"]
        repo = repo_context["Repo"]
        print(f"Analyzing repository: {owner}/{repo}", file=sys.stderr)

        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=args.since)

        print(
            f"Querying workflow runs from {start_date.strftime('%Y-%m-%d')} "
            f"to {end_date.strftime('%Y-%m-%d')}",
            file=sys.stderr,
        )

        runs = get_workflow_runs(owner, repo, start_date, workflows)

        if not runs:
            print("No workflow runs found in the specified period", file=sys.stderr)
            return 0

        print(f"Analyzing {len(runs)} workflow runs for overlaps", file=sys.stderr)
        overlaps = get_overlapping_runs(runs)

        print("Calculating metrics", file=sys.stderr)
        metrics = get_coalescing_metrics(runs, overlaps)

        if args.output == "json":
            result = {
                "Metrics": {
                    "TotalRuns": metrics.total_runs,
                    "CancelledRuns": metrics.cancelled_runs,
                    "RaceConditions": metrics.race_conditions,
                    "SuccessfulCoalescing": metrics.successful_coalescing,
                    "CoalescingEffectiveness": metrics.coalescing_effectiveness,
                    "RaceConditionRate": metrics.race_condition_rate,
                    "AvgCancellationTime": metrics.avg_cancellation_time,
                },
                "Period": {
                    "StartDate": start_date.strftime("%Y-%m-%d"),
                    "EndDate": end_date.strftime("%Y-%m-%d"),
                },
                "Runs": len(runs),
                "Overlaps": len(overlaps),
            }
            json_str = json.dumps(result, indent=2)
            if args.output_path:
                _write_output(args.output_path, json_str)
                print(f"JSON report saved to: {args.output_path}", file=sys.stderr)
            else:
                print(json_str)

        elif args.output == "summary":
            print("\n=== Coalescing Metrics Summary ===", file=sys.stderr)
            print(f"Total Runs: {metrics.total_runs}", file=sys.stderr)
            print(f"Cancelled Runs: {metrics.cancelled_runs}", file=sys.stderr)
            print(f"Race Conditions: {metrics.race_conditions}", file=sys.stderr)
            eff_mark = "+" if metrics.coalescing_effectiveness >= 90 else "X"
            print(
                f"Coalescing Effectiveness: {metrics.coalescing_effectiveness}% {eff_mark}",
                file=sys.stderr,
            )
            race_mark = "+" if metrics.race_condition_rate <= 10 else "X"
            print(
                f"Race Condition Rate: {metrics.race_condition_rate}% {race_mark}",
                file=sys.stderr,
            )
            cancel_mark = "+" if metrics.avg_cancellation_time <= 5 else "X"
            print(
                f"Avg Cancellation Time: {metrics.avg_cancellation_time}s {cancel_mark}",
                file=sys.stderr,
            )

        else:  # markdown
            report = format_markdown_report(
                metrics, runs, overlaps, start_date, end_date, workflows,
            )
            if args.output_path:
                _write_output(args.output_path, report)
                print(
                    f"Markdown report saved to: {args.output_path}",
                    file=sys.stderr,
                )
            else:
                print(report)

    except SystemExit:
        raise
    except Exception as exc:
        print(f"Failed to measure workflow coalescing: {exc}", file=sys.stderr)
        return 1

    return 0


def _write_output(path: str, content: str) -> None:
    """Write content to file, creating parent directories as needed."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
