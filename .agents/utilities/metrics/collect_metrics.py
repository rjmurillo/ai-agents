#!/usr/bin/env python3
"""
Agent Metrics Collection Utility

Collects and reports metrics on agent usage from git history and PR data.
Implements the 8 key metrics defined in docs/agent-metrics.md.

Usage:
    python collect_metrics.py [--since DAYS] [--output FORMAT]

Options:
    --since DAYS    Number of days to analyze (default: 30)
    --output FORMAT Output format: json, markdown, summary (default: summary)
    --repo PATH     Repository path (default: current directory)
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# Agent patterns to detect in commit messages and PR descriptions
AGENT_PATTERNS = [
    r"(?i)\b(orchestrator|analyst|architect|implementer|security|qa|devops|"
    r"critic|planner|explainer|task-generator|high-level-advisor|"
    r"independent-thinker|memory|skillbook|retrospective|roadmap|"
    r"pr-comment-responder)\b\s*(agent)?",
    r"(?i)reviewed\s+by:?\s*(security|architect|analyst|qa|implementer)",
    r"(?i)agent:\s*(\w+)",
    r"(?i)\[(\w+)-agent\]",
]

# Infrastructure file patterns (from Issue #9)
INFRASTRUCTURE_PATTERNS = [
    r"^\.github/workflows/.*\.(yml|yaml)$",
    r"^\.github/actions/",
    r"^\.githooks/",
    r"^build/",
    r"^scripts/",
    r"Dockerfile",
    r"docker-compose",
    r"\.tf$",
    r"\.tfvars$",
    r"\.env",
    r"\.agents/",
]

# Commit type patterns (conventional commits)
COMMIT_TYPE_PATTERNS = {
    "feature": r"^feat(\(.+\))?:",
    "fix": r"^fix(\(.+\))?:",
    "docs": r"^docs(\(.+\))?:",
    "refactor": r"^refactor(\(.+\))?:",
    "test": r"^test(\(.+\))?:",
    "chore": r"^chore(\(.+\))?:",
    "ci": r"^ci(\(.+\))?:",
    "perf": r"^perf(\(.+\))?:",
    "style": r"^style(\(.+\))?:",
}


def run_git_command(args: list[str], repo_path: str = ".") -> str:
    """Run a git command and return output."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {e.stderr}", file=sys.stderr)
        return ""


def get_commits_since(days: int, repo_path: str = ".") -> list[dict[str, Any]]:
    """Get commits from the last N days."""
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # Get commit data in a parseable format
    log_format = "%H|%s|%an|%ae|%ad"
    output = run_git_command(
        ["log", f"--since={since_date}", f"--format={log_format}", "--date=short"],
        repo_path,
    )

    if not output:
        return []

    commits = []
    for line in output.split("\n"):
        if not line.strip():
            continue
        parts = line.split("|", 4)
        if len(parts) >= 5:
            commits.append({
                "hash": parts[0],
                "subject": parts[1],
                "author": parts[2],
                "email": parts[3],
                "date": parts[4],
            })

    return commits


def get_commit_files(commit_hash: str, repo_path: str = ".") -> list[str]:
    """Get files changed in a commit."""
    output = run_git_command(
        ["diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
        repo_path,
    )
    return [f for f in output.split("\n") if f.strip()]


def detect_agents_in_text(text: str) -> list[str]:
    """Detect agent references in text."""
    agents = set()
    for pattern in AGENT_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                agent = match[0].lower()
            else:
                agent = match.lower()
            if agent and agent != "agent":
                agents.add(agent)
    return list(agents)


def classify_commit_type(subject: str) -> str:
    """Classify commit by conventional commit type."""
    for commit_type, pattern in COMMIT_TYPE_PATTERNS.items():
        if re.match(pattern, subject, re.IGNORECASE):
            return commit_type
    return "other"


def is_infrastructure_file(filepath: str) -> bool:
    """Check if file matches infrastructure patterns."""
    for pattern in INFRASTRUCTURE_PATTERNS:
        if re.search(pattern, filepath):
            return True
    return False


def collect_metrics(repo_path: str = ".", days: int = 30) -> dict[str, Any]:
    """Collect all 8 key metrics."""
    commits = get_commits_since(days, repo_path)

    # Initialize metric collectors
    agent_invocations: Counter = Counter()
    commits_with_agents = 0
    commits_by_type: Counter = Counter()
    commits_with_agent_by_type: defaultdict = defaultdict(int)
    infrastructure_commits = 0
    infrastructure_with_security = 0

    for commit in commits:
        # Get commit details
        files = get_commit_files(commit["hash"], repo_path)
        subject = commit["subject"]
        commit_type = classify_commit_type(subject)

        # Detect agents
        agents = detect_agents_in_text(subject)

        # Metric 1 & 5: Agent invocation tracking
        for agent in agents:
            agent_invocations[agent] += 1

        # Metric 2: Agent coverage
        commits_by_type[commit_type] += 1
        if agents:
            commits_with_agents += 1
            commits_with_agent_by_type[commit_type] += 1

        # Metric 4: Infrastructure review rate
        has_infra = any(is_infrastructure_file(f) for f in files)
        if has_infra:
            infrastructure_commits += 1
            if "security" in agents:
                infrastructure_with_security += 1

    total_commits = len(commits)
    total_invocations = sum(agent_invocations.values())

    # Calculate metrics
    metrics = {
        "period": {
            "days": days,
            "start_date": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
            "end_date": datetime.now().strftime("%Y-%m-%d"),
            "total_commits": total_commits,
        },

        # Metric 1: Invocation Rate by Agent
        "metric_1_invocation_rate": {
            "agents": {
                agent: {
                    "count": count,
                    "rate": round(count / total_invocations * 100, 1) if total_invocations > 0 else 0,
                }
                for agent, count in agent_invocations.most_common()
            },
            "total_invocations": total_invocations,
        },

        # Metric 2: Agent Coverage
        "metric_2_coverage": {
            "total_commits": total_commits,
            "commits_with_agent": commits_with_agents,
            "coverage_rate": round(commits_with_agents / total_commits * 100, 1) if total_commits > 0 else 0,
            "target": 50,
            "by_type": {
                commit_type: {
                    "total": commits_by_type[commit_type],
                    "with_agent": commits_with_agent_by_type[commit_type],
                    "rate": round(
                        commits_with_agent_by_type[commit_type] / commits_by_type[commit_type] * 100, 1
                    ) if commits_by_type[commit_type] > 0 else 0,
                }
                for commit_type in commits_by_type
            },
        },

        # Metric 4: Infrastructure Code Review Rate
        "metric_4_infrastructure_review": {
            "infrastructure_commits": infrastructure_commits,
            "with_security_review": infrastructure_with_security,
            "review_rate": round(
                infrastructure_with_security / infrastructure_commits * 100, 1
            ) if infrastructure_commits > 0 else 0,
            "target": 100,
        },

        # Metric 5: Usage Distribution
        "metric_5_distribution": {
            agent: round(count / total_invocations * 100, 1) if total_invocations > 0 else 0
            for agent, count in agent_invocations.most_common()
        },
    }

    # Add status indicators
    coverage_rate = metrics["metric_2_coverage"]["coverage_rate"]
    metrics["metric_2_coverage"]["status"] = "on_track" if coverage_rate >= 50 else "behind"

    infra_rate = metrics["metric_4_infrastructure_review"]["review_rate"]
    metrics["metric_4_infrastructure_review"]["status"] = "on_track" if infra_rate >= 100 else "behind"

    return metrics


def format_summary(metrics: dict[str, Any]) -> str:
    """Format metrics as human-readable summary."""
    lines = [
        "=" * 60,
        "AGENT METRICS SUMMARY",
        "=" * 60,
        "",
        f"Period: {metrics['period']['start_date']} to {metrics['period']['end_date']}",
        f"Total Commits Analyzed: {metrics['period']['total_commits']}",
        "",
        "-" * 40,
        "METRIC 1: INVOCATION RATE BY AGENT",
        "-" * 40,
    ]

    invocations = metrics["metric_1_invocation_rate"]["agents"]
    if invocations:
        for agent, data in invocations.items():
            lines.append(f"  {agent:20} {data['count']:4} ({data['rate']:5.1f}%)")
    else:
        lines.append("  No agent invocations detected")

    lines.extend([
        "",
        "-" * 40,
        "METRIC 2: AGENT COVERAGE",
        "-" * 40,
    ])

    coverage = metrics["metric_2_coverage"]
    lines.append(f"  Overall: {coverage['coverage_rate']:.1f}% (Target: {coverage['target']}%)")
    lines.append(f"  Status: {coverage['status'].upper()}")

    lines.extend([
        "",
        "-" * 40,
        "METRIC 4: INFRASTRUCTURE REVIEW RATE",
        "-" * 40,
    ])

    infra = metrics["metric_4_infrastructure_review"]
    lines.append(f"  Infrastructure Commits: {infra['infrastructure_commits']}")
    lines.append(f"  With Security Review: {infra['with_security_review']}")
    lines.append(f"  Review Rate: {infra['review_rate']:.1f}% (Target: {infra['target']}%)")
    lines.append(f"  Status: {infra['status'].upper()}")

    lines.extend([
        "",
        "=" * 60,
    ])

    return "\n".join(lines)


def format_markdown(metrics: dict[str, Any]) -> str:
    """Format metrics as markdown report."""
    lines = [
        "# Agent Metrics Report",
        "",
        "## Report Period",
        "",
        f"**From**: {metrics['period']['start_date']}",
        f"**To**: {metrics['period']['end_date']}",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "| Metric | Current | Target | Status |",
        "|--------|---------|--------|--------|",
    ]

    coverage = metrics["metric_2_coverage"]
    infra = metrics["metric_4_infrastructure_review"]

    lines.append(
        f"| Agent Coverage | {coverage['coverage_rate']:.1f}% | {coverage['target']}% | "
        f"{'On Track' if coverage['status'] == 'on_track' else 'Behind'} |"
    )
    lines.append(
        f"| Infrastructure Review | {infra['review_rate']:.1f}% | {infra['target']}% | "
        f"{'On Track' if infra['status'] == 'on_track' else 'Behind'} |"
    )

    lines.extend([
        "",
        "---",
        "",
        "## Metric 1: Invocation Rate by Agent",
        "",
        "| Agent | Invocations | Rate |",
        "|-------|-------------|------|",
    ])

    for agent, data in metrics["metric_1_invocation_rate"]["agents"].items():
        lines.append(f"| {agent} | {data['count']} | {data['rate']:.1f}% |")

    if not metrics["metric_1_invocation_rate"]["agents"]:
        lines.append("| *No agents detected* | 0 | 0% |")

    lines.extend([
        "",
        f"**Total Invocations**: {metrics['metric_1_invocation_rate']['total_invocations']}",
        "",
        "---",
        "",
        "## Metric 2: Agent Coverage by Commit Type",
        "",
        "| Commit Type | Total | With Agent | Coverage |",
        "|-------------|-------|------------|----------|",
    ])

    for commit_type, data in metrics["metric_2_coverage"]["by_type"].items():
        lines.append(
            f"| {commit_type} | {data['total']} | {data['with_agent']} | {data['rate']:.1f}% |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Metric 4: Infrastructure Review Rate",
        "",
        f"- **Infrastructure Commits**: {infra['infrastructure_commits']}",
        f"- **With Security Review**: {infra['with_security_review']}",
        f"- **Review Rate**: {infra['review_rate']:.1f}%",
        f"- **Target**: {infra['target']}%",
        "",
        "---",
        "",
        "*Generated by collect_metrics.py*",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Collect agent invocation metrics from git history"
    )
    parser.add_argument(
        "--since",
        type=int,
        default=30,
        help="Number of days to analyze (default: 30)",
    )
    parser.add_argument(
        "--output",
        choices=["json", "markdown", "summary"],
        default="summary",
        help="Output format (default: summary)",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=".",
        help="Repository path (default: current directory)",
    )

    args = parser.parse_args()

    # Validate repo path
    repo_path = Path(args.repo).resolve()
    if not (repo_path / ".git").exists():
        print(f"Error: {repo_path} is not a git repository", file=sys.stderr)
        sys.exit(1)

    # Collect metrics
    metrics = collect_metrics(str(repo_path), args.since)

    # Output in requested format
    if args.output == "json":
        print(json.dumps(metrics, indent=2))
    elif args.output == "markdown":
        print(format_markdown(metrics))
    else:
        print(format_summary(metrics))


if __name__ == "__main__":
    main()
