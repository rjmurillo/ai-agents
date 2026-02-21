#!/usr/bin/env python3
"""Aggregate PR review comment statistics by reviewer and update Serena memory.

Queries all PRs (open and closed) for review comments, calculates signal quality
metrics per reviewer, and updates the pr-comment-responder-skills memory file.

Exit codes (ADR-035):
    0 - Success
    1 - Invalid parameters / logic error
    2 - API / external error
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
)
sys.path.insert(0, workspace)

from scripts.github_core.api import (  # noqa: E402
    check_workflow_rate_limit,
    get_all_prs_with_comments,
    resolve_repo_params,
)
from scripts.llm_classification import (  # noqa: E402
    LLMClassifier,
    LLMFallbackConfig,
    get_default_classifier,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SELF_COMMENT_EXCLUDED_AUTHORS = ["dependabot[bot]"]

HEURISTICS: dict[str, float | int] = {
    "fixed_in_reply": 1.0,
    "wont_fix_reply": 0.5,
    "severity_high": 0.3,
    "potential_null": 0.2,
    "severity_low": -0.1,
    "unused_remove": -0.2,
    "no_reply_after_days": -0.3,
    "no_reply_threshold": 7,
}

MEMORY_PATH = ".serena/memories/pr-comment-responder-skills.md"

TREND_THRESHOLDS: dict[str, float] = {
    "improving": 0.05,
    "declining": -0.05,
}

# ---------------------------------------------------------------------------
# Regex patterns for actionability scoring
# ---------------------------------------------------------------------------

FIXED_PATTERN = re.compile(
    r"fixed\s+in|implemented|addressed|resolved", re.IGNORECASE
)
WONTFIX_PATTERN = re.compile(
    r"won't\s*fix|wontfix|intentional|by\s*design|not\s*a\s*bug", re.IGNORECASE
)
HIGH_SEVERITY_PATTERN = re.compile(
    r"critical|high\s*severity|security|vulnerability|cwe-|injection", re.IGNORECASE
)
LOW_SEVERITY_PATTERN = re.compile(
    r"low\s*severity|style|nit:|minor|cosmetic", re.IGNORECASE
)
NULL_PATTERN = re.compile(
    r"potential\s*null|null\s*reference|null\s*check", re.IGNORECASE
)
UNUSED_PATTERN = re.compile(
    r"unused|remove\s*(this|it|the)|dead\s*code", re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CommentData:
    """A single review comment with thread context."""

    pr_number: int
    body: str
    created_at: str
    path: str
    is_resolved: bool
    is_outdated: bool
    thread_comments: list[dict[str, Any]]


@dataclass
class ActionabilityResult:
    """Result of actionability scoring for a comment."""

    score: float
    reasons: list[str]
    is_actionable: bool
    used_llm_fallback: bool = False


@dataclass
class ReviewerStats:
    """Aggregated stats for a single reviewer."""

    total_comments: int = 0
    prs_with_comments: set[int] = field(default_factory=set)
    comments: list[CommentData] = field(default_factory=list)
    verified_actionable: int = 0


@dataclass
class SignalStats:
    """Signal quality statistics for a reviewer."""

    total_comments: int
    prs_with_comments: int
    verified_actionable: int
    estimated_actionable: int
    signal_rate: float
    trend: str
    last_30_days_comments: int
    last_30_days_signal_rate: float


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def get_comments_by_reviewer(
    prs: list[dict[str, Any]],
) -> dict[str, ReviewerStats]:
    """Group review comments by reviewer login. Exclude self-comments.

    Authors CAN review other authors' PRs. Only self-comments (reviewer
    commenting on their own PR) are excluded.

    Args:
        prs: List of PR dicts from GraphQL with reviewThreads.

    Returns:
        Dict mapping reviewer login to ReviewerStats.
    """
    reviewer_stats: dict[str, ReviewerStats] = {}

    for pr in prs:
        pr_author = (pr.get("author") or {}).get("login", "")

        threads = pr.get("reviewThreads", {}).get("nodes", [])
        for thread in threads:
            is_resolved = thread.get("isResolved", False)
            is_outdated = thread.get("isOutdated", False)
            comments_nodes = thread.get("comments", {}).get("nodes", [])

            for comment in comments_nodes:
                comment_author = (comment.get("author") or {}).get("login", "")

                # Skip self-comments (reviewer commenting on their own PR)
                if comment_author == pr_author:
                    continue

                if comment_author not in reviewer_stats:
                    reviewer_stats[comment_author] = ReviewerStats()

                stats = reviewer_stats[comment_author]
                stats.total_comments += 1
                stats.prs_with_comments.add(pr.get("number", 0))
                stats.comments.append(
                    CommentData(
                        pr_number=pr.get("number", 0),
                        body=comment.get("body", ""),
                        created_at=comment.get("createdAt", ""),
                        path=comment.get("path", ""),
                        is_resolved=is_resolved,
                        is_outdated=is_outdated,
                        thread_comments=comments_nodes,
                    )
                )

    return reviewer_stats


def get_actionability_score(
    comment_data: CommentData,
    heuristics: dict[str, float | int] | None = None,
    llm_classifier: LLMClassifier | None = None,
) -> ActionabilityResult:
    """Calculate actionability score for a comment based on heuristics.

    Score starts at 0.5 (neutral) and adjusts based on matched patterns.
    Final score is clamped to [0, 1]. IsActionable = score >= 0.5.

    When the heuristic score falls in the low-confidence range (default 0.4-0.6),
    an LLM fallback is used if configured and available.

    Args:
        comment_data: The comment to score.
        heuristics: Scoring heuristics. Uses module default if None.
        llm_classifier: Optional LLM classifier for low-confidence fallback.

    Returns:
        ActionabilityResult with score, reasons, and is_actionable flag.
    """
    if heuristics is None:
        heuristics = HEURISTICS

    score = 0.5
    reasons: list[str] = []

    body = comment_data.body.lower()
    thread_comments = comment_data.thread_comments

    # Check for "Fixed in" reply in thread
    has_fixed_reply = any(
        FIXED_PATTERN.search(c.get("body", "")) for c in thread_comments
    )
    if has_fixed_reply:
        score += float(heuristics["fixed_in_reply"])
        reasons.append("FixedInReply")

    # Check for "Won't fix" reply in thread
    has_wontfix_reply = any(
        WONTFIX_PATTERN.search(c.get("body", "")) for c in thread_comments
    )
    if has_wontfix_reply:
        score += float(heuristics["wont_fix_reply"])
        reasons.append("WontFixReply")

    # Severity indicators in comment body
    if HIGH_SEVERITY_PATTERN.search(body):
        score += float(heuristics["severity_high"])
        reasons.append("SeverityHigh")

    if LOW_SEVERITY_PATTERN.search(body):
        score += float(heuristics["severity_low"])
        reasons.append("SeverityLow")

    # Common patterns
    if NULL_PATTERN.search(body):
        score += float(heuristics["potential_null"])
        reasons.append("PotentialNull")

    if UNUSED_PATTERN.search(body):
        score += float(heuristics["unused_remove"])
        reasons.append("UnusedRemove")

    # No reply after threshold days (only if not resolved and no fix/wontfix reply)
    if not comment_data.is_resolved and not has_fixed_reply and not has_wontfix_reply:
        try:
            created_at = datetime.fromisoformat(
                comment_data.created_at.replace("Z", "+00:00")
            )
            now = datetime.now(UTC)
            days_since = (now - created_at).days
            threshold = int(heuristics["no_reply_threshold"])
            if days_since >= threshold:
                score += float(heuristics["no_reply_after_days"])
                reasons.append("NoReplyAfterDays")
        except (ValueError, TypeError):
            pass

    # Clamp score between 0 and 1
    score = max(0.0, min(1.0, score))

    # LLM fallback for low-confidence scores
    used_llm = False
    if llm_classifier is not None and llm_classifier.should_use_fallback(score):
        llm_result = llm_classifier.classify(comment_data.body)
        if llm_result is not None:
            used_llm = True
            reasons.append("LLMFallback")
            if llm_result.from_cache:
                reasons.append("LLMCached")
            # Use LLM result when confidence is higher than heuristic ambiguity
            if llm_result.confidence >= 0.7:
                return ActionabilityResult(
                    score=0.9 if llm_result.is_actionable else 0.1,
                    reasons=reasons,
                    is_actionable=llm_result.is_actionable,
                    used_llm_fallback=True,
                )

    return ActionabilityResult(
        score=score,
        reasons=reasons,
        is_actionable=score >= 0.5,
        used_llm_fallback=used_llm,
    )


def get_reviewer_signal_stats(
    reviewer_stats: dict[str, ReviewerStats],
    heuristics: dict[str, float | int] | None = None,
    llm_classifier: LLMClassifier | None = None,
) -> dict[str, SignalStats]:
    """Calculate signal quality statistics for each reviewer.

    Args:
        reviewer_stats: Dict mapping reviewer login to ReviewerStats.
        heuristics: Scoring heuristics. Uses module default if None.
        llm_classifier: Optional LLM classifier for low-confidence fallback.

    Returns:
        Dict mapping reviewer login to SignalStats.
    """
    if heuristics is None:
        heuristics = HEURISTICS

    results: dict[str, SignalStats] = {}
    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)

    for reviewer, stats in reviewer_stats.items():
        actionable_count = 0
        last_30_days_count = 0
        last_30_days_actionable = 0

        for comment in stats.comments:
            score_result = get_actionability_score(comment, heuristics, llm_classifier)

            if score_result.is_actionable:
                actionable_count += 1

            # Track last 30 days
            try:
                comment_date = datetime.fromisoformat(
                    comment.created_at.replace("Z", "+00:00")
                )
                if comment_date >= thirty_days_ago:
                    last_30_days_count += 1
                    if score_result.is_actionable:
                        last_30_days_actionable += 1
            except (ValueError, TypeError):
                pass

        signal_rate = (
            round(actionable_count / stats.total_comments, 2)
            if stats.total_comments > 0
            else 0.0
        )

        last_30_signal_rate = (
            round(last_30_days_actionable / last_30_days_count, 2)
            if last_30_days_count > 0
            else 0.0
        )

        # Determine trend: require minimum sample sizes
        trend = "stable"
        if last_30_days_count >= 5 and stats.total_comments >= 10:
            rate_diff = last_30_signal_rate - signal_rate
            if rate_diff >= TREND_THRESHOLDS["improving"]:
                trend = "improving"
            elif rate_diff <= TREND_THRESHOLDS["declining"]:
                trend = "declining"

        results[reviewer] = SignalStats(
            total_comments=stats.total_comments,
            prs_with_comments=len(stats.prs_with_comments),
            verified_actionable=stats.verified_actionable,
            estimated_actionable=actionable_count,
            signal_rate=signal_rate,
            trend=trend,
            last_30_days_comments=last_30_days_count,
            last_30_days_signal_rate=last_30_signal_rate,
        )

    return results


def update_serena_memory(
    stats: dict[str, SignalStats],
    prs_analyzed: int,
    days_analyzed: int,
    memory_path: str,
) -> bool:
    """Update the Serena memory file with computed statistics.

    Updates the Per-Reviewer Performance table in the memory file.

    Args:
        stats: Reviewer statistics from get_reviewer_signal_stats.
        prs_analyzed: Number of PRs analyzed.
        days_analyzed: Number of days analyzed.
        memory_path: Path to the Serena memory file.

    Returns:
        True if update succeeded, False if file not found.
    """
    if not os.path.isfile(memory_path):
        logger.warning("Memory file not found: %s", memory_path)
        return False

    with open(memory_path, encoding="utf-8") as f:
        content = f.read()

    # Build the new Per-Reviewer Performance table
    table_header = (
        f"## Per-Reviewer Performance (Cumulative)\n"
        f"\n"
        f"Aggregated from {prs_analyzed} PRs over last {days_analyzed} days.\n"
        f"\n"
        f"| Reviewer | PRs | Comments | Actionable | Signal | Trend |\n"
        f"|----------|-----|----------|------------|--------|-------|"
    )

    # Sort by signal rate descending
    sorted_reviewers = sorted(
        stats.items(), key=lambda item: item[1].signal_rate, reverse=True
    )

    rows: list[str] = []
    for reviewer, data in sorted_reviewers:
        signal_percent = round(data.signal_rate * 100)
        signal_display = (
            f"**{signal_percent}%**" if signal_percent >= 90 else f"{signal_percent}%"
        )
        trend_icon = {"improving": "\u2191", "declining": "\u2193"}.get(
            data.trend, "\u2192"
        )

        row = (
            f"| {reviewer} | {data.prs_with_comments} | {data.total_comments} "
            f"| {data.estimated_actionable} | {signal_display} | {trend_icon} |"
        )
        rows.append(row)

    new_table = table_header + "\n" + "\n".join(rows)

    # Replace existing Per-Reviewer Performance section
    pattern = r"(?s)## Per-Reviewer Performance.*?(?=## |\Z)"

    if re.search(pattern, content):
        content = re.sub(pattern, new_table + "\n", content)
    else:
        # Insert after Overview section if Per-Reviewer section doesn't exist
        content = re.sub(
            r"(## Overview.*?)(\n## )",
            rf"\1\n\n{new_table}\n\2",
            content,
        )

    with open(memory_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("Updated Serena memory: %s", memory_path)
    logger.info("  Reviewers: %d", len(stats))

    return True


# ---------------------------------------------------------------------------
# GitHub Actions step summary
# ---------------------------------------------------------------------------


def _write_step_summary(
    signal_stats: dict[str, SignalStats],
    days_back: int,
    prs_count: int,
    total_comments: int,
) -> None:
    """Write GitHub Actions step summary if GITHUB_STEP_SUMMARY is set."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    sorted_reviewers = sorted(
        signal_stats.items(), key=lambda item: item[1].signal_rate, reverse=True
    )

    lines = [
        "## Reviewer Signal Stats Update",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Days Analyzed | {days_back} |",
        f"| PRs Analyzed | {prs_count} |",
        f"| Reviewers Found | {len(signal_stats)} |",
        f"| Total Comments | {total_comments} |",
        "",
        "### Reviewer Rankings",
        "",
        "| Reviewer | Signal Rate | Trend | Comments |",
        "|----------|-------------|-------|----------|",
    ]

    for reviewer, data in sorted_reviewers:
        signal_percent = round(data.signal_rate * 100)
        trend_icon = {"improving": "\u2191", "declining": "\u2193"}.get(
            data.trend, "\u2192"
        )
        lines.append(
            f"| {reviewer} | {signal_percent}% | {trend_icon} | {data.total_comments} |"
        )

    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate PR review comment statistics by reviewer and update Serena memory."
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=28,
        help="Days of PR history to analyze (default: 28, range: 1-365)",
    )
    parser.add_argument(
        "--owner",
        default="",
        help="Repository owner (inferred from git remote if omitted)",
    )
    parser.add_argument(
        "--repo",
        default="",
        help="Repository name (inferred from git remote if omitted)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )

    parser = _build_parser()
    args = parser.parse_args(argv)

    # Validate days-back range
    if args.days_back < 1 or args.days_back > 365:
        logger.error("--days-back must be between 1 and 365, got %d", args.days_back)
        return 1

    start_time = time.monotonic()

    logger.info("Starting reviewer signal stats aggregation")
    logger.info("DaysBack: %d", args.days_back)

    # Check rate limit
    try:
        rate_result = check_workflow_rate_limit(
            resource_thresholds={"core": 200, "graphql": 100}
        )
        if not rate_result.success:
            logger.error("Insufficient API rate limit. Exiting.")
            return 2
    except RuntimeError:
        logger.exception("Failed to check rate limit")
        return 2

    # Resolve repo info
    try:
        repo_params = resolve_repo_params(args.owner, args.repo)
    except SystemExit:
        raise
    except Exception:
        logger.exception("Failed to resolve repository parameters")
        return 2

    owner = repo_params.owner
    repo = repo_params.repo
    logger.info("Repository: %s/%s", owner, repo)

    # Calculate date range
    since = datetime.now(UTC) - timedelta(days=args.days_back)

    # Fetch PRs with comments
    try:
        prs = get_all_prs_with_comments(owner, repo, since)
    except RuntimeError:
        logger.exception("Failed to fetch PRs")
        return 2

    if not prs:
        logger.warning("No PRs with review comments found in the last %d days", args.days_back)
        return 0

    # Group comments by reviewer
    reviewer_stats = get_comments_by_reviewer(prs)

    if not reviewer_stats:
        logger.warning("No reviewer comments found (excluding self-comments)")
        return 0

    # Initialize LLM classifier for low-confidence fallback
    llm_config = LLMFallbackConfig.from_env()
    llm_classifier: LLMClassifier | None = None
    if llm_config.enabled:
        try:
            llm_classifier = get_default_classifier()
            logger.info(
                "LLM fallback enabled (threshold: %.1f-%.1f)",
                llm_config.low_confidence_min,
                llm_config.low_confidence_max,
            )
        except Exception:
            logger.warning("LLM fallback unavailable, using heuristics only")

    # Calculate signal quality stats
    signal_stats = get_reviewer_signal_stats(reviewer_stats, llm_classifier=llm_classifier)

    # Calculate total comments for summary
    total_comments = sum(s.total_comments for s in signal_stats.values())

    # Update Serena memory (source of truth)
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        repo_root = result.stdout.strip() if result.returncode == 0 else "."
    except (subprocess.TimeoutExpired, FileNotFoundError):
        repo_root = "."

    memory_full_path = os.path.join(repo_root, MEMORY_PATH)
    update_serena_memory(signal_stats, len(prs), args.days_back, memory_full_path)

    # Summary
    duration = time.monotonic() - start_time
    logger.info("---")
    logger.info("=== Aggregation Complete ===")
    logger.info("PRs analyzed: %d", len(prs))
    logger.info("Reviewers found: %d", len(signal_stats))
    logger.info("Total comments: %d", total_comments)
    logger.info("Duration: %.1f seconds", duration)

    # GitHub Actions step summary
    _write_step_summary(signal_stats, args.days_back, len(prs), total_comments)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
