#!/usr/bin/env python3
"""Agent Metrics Collection Utility.

Collects and reports metrics on agent usage from git history.
Implements the 8 key metrics defined in docs/agent-metrics.md.

EXIT CODES (ADR-035):
    0 - Success: Metrics collected and output successfully
    1 - Error: Path not found or not a git repository
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

AGENT_PATTERNS = [
    r"(?i)\b(orchestrator|analyst|architect|implementer|security|qa|devops|critic|"
    r"milestone-planner|planner|explainer|task-decomposer|task-generator|"
    r"backlog-generator|high-level-advisor|independent-thinker|memory|"
    r"skillbook|retrospective|roadmap|pr-comment-responder)\b\s*(agent)?",
    r"(?i)reviewed\s+by:?\s*(security|architect|analyst|qa|implementer)",
    r"(?i)agent:\s*(\w+)",
    r"(?i)\[(\w+)-agent\]",
]

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


def get_commits_since(days: int, path: str) -> list[dict]:
    """Get commits from git log since a given number of days ago."""
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    log_format = "%H|%s|%an|%ae|%ad"

    try:
        result = subprocess.run(
            ["git", "-C", path, "log", f"--since={since_date}", f"--format={log_format}", "--date=short"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    if not result.stdout.strip():
        return []

    commits = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 4)
        if len(parts) >= 5:
            commits.append({
                "Hash": parts[0],
                "Subject": parts[1],
                "Author": parts[2],
                "Email": parts[3],
                "Date": parts[4],
            })
    return commits


def get_commit_files(commit_hash: str, path: str) -> list[str]:
    """Get files changed in a commit."""
    try:
        result = subprocess.run(
            ["git", "-C", path, "diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    return [f for f in result.stdout.strip().splitlines() if f.strip()]


def find_agents_in_text(text: str) -> list[str]:
    """Find agent names mentioned in text."""
    agents: dict[str, bool] = {}
    for pattern in AGENT_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            agent = match.group(1).lower()
            if agent and agent != "agent":
                agents[agent] = True
    return list(agents.keys())


def get_commit_type(subject: str) -> str:
    """Determine commit type from conventional commit message."""
    for commit_type, pattern in COMMIT_TYPE_PATTERNS.items():
        if re.search(pattern, subject):
            return commit_type
    return "other"


def is_infrastructure_file(file_path: str) -> bool:
    """Check if a file matches infrastructure patterns."""
    for pattern in INFRASTRUCTURE_PATTERNS:
        if re.search(pattern, file_path):
            return True
    return False


def get_metrics(path: str, days: int) -> dict:
    """Collect all metrics."""
    commits = get_commits_since(days, path)
    now = datetime.now()

    agent_invocations: dict[str, int] = {}
    commits_with_agents = 0
    commits_by_type: dict[str, int] = {}
    commits_with_agent_by_type: dict[str, int] = {}
    infrastructure_commits = 0
    infrastructure_with_security = 0

    for commit in commits:
        files = get_commit_files(commit["Hash"], path)
        subject = commit["Subject"]
        commit_type = get_commit_type(subject)

        agents = find_agents_in_text(subject)

        for agent in agents:
            agent_invocations[agent] = agent_invocations.get(agent, 0) + 1

        commits_by_type.setdefault(commit_type, 0)
        commits_with_agent_by_type.setdefault(commit_type, 0)
        commits_by_type[commit_type] += 1

        if agents:
            commits_with_agents += 1
            commits_with_agent_by_type[commit_type] += 1

        has_infra = any(is_infrastructure_file(f) for f in files)
        if has_infra:
            infrastructure_commits += 1
            if "security" in agents:
                infrastructure_with_security += 1

    total_commits = len(commits)
    total_invocations = sum(agent_invocations.values())

    coverage_rate = round(commits_with_agents / total_commits * 100, 1) if total_commits > 0 else 0
    infra_rate = (
        round(infrastructure_with_security / infrastructure_commits * 100, 1)
        if infrastructure_commits > 0
        else 0
    )

    metrics: dict = {
        "period": {
            "days": days,
            "start_date": (now - timedelta(days=days)).strftime("%Y-%m-%d"),
            "end_date": now.strftime("%Y-%m-%d"),
            "total_commits": total_commits,
        },
        "metric_1_invocation_rate": {
            "agents": {},
            "total_invocations": total_invocations,
        },
        "metric_2_coverage": {
            "total_commits": total_commits,
            "commits_with_agent": commits_with_agents,
            "coverage_rate": coverage_rate,
            "target": 50,
            "by_type": {},
            "status": "on_track" if coverage_rate >= 50 else "behind",
        },
        "metric_4_infrastructure_review": {
            "infrastructure_commits": infrastructure_commits,
            "with_security_review": infrastructure_with_security,
            "review_rate": infra_rate,
            "target": 100,
            "status": (
                "on_track"
                if infrastructure_commits == 0
                or infrastructure_with_security / infrastructure_commits >= 1
                else "behind"
            ),
        },
        "metric_5_distribution": {},
    }

    for agent in sorted(agent_invocations, key=lambda a: agent_invocations[a], reverse=True):
        count = agent_invocations[agent]
        rate = round(count / total_invocations * 100, 1) if total_invocations > 0 else 0
        metrics["metric_1_invocation_rate"]["agents"][agent] = {"count": count, "rate": rate}
        metrics["metric_5_distribution"][agent] = rate

    for commit_type, total in commits_by_type.items():
        with_agent = commits_with_agent_by_type.get(commit_type, 0)
        metrics["metric_2_coverage"]["by_type"][commit_type] = {
            "total": total,
            "with_agent": with_agent,
            "rate": round(with_agent / total * 100, 1) if total > 0 else 0,
        }

    return metrics


def format_summary(metrics: dict) -> str:
    """Format metrics as a human-readable summary."""
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

    agents = metrics["metric_1_invocation_rate"]["agents"]
    if agents:
        for agent, data in agents.items():
            lines.append(f"  {agent:<20} {data['count']:>4} ({data['rate']:>5.1f}%)")
    else:
        lines.append("  No agent invocations detected")

    lines.extend([
        "",
        "-" * 40,
        "METRIC 2: AGENT COVERAGE",
        "-" * 40,
    ])

    coverage = metrics["metric_2_coverage"]
    lines.append(f"  Overall: {coverage['coverage_rate']}% (Target: {coverage['target']}%)")
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
    lines.append(f"  Review Rate: {infra['review_rate']}% (Target: {infra['target']}%)")
    lines.append(f"  Status: {infra['status'].upper()}")

    lines.extend(["", "=" * 60])

    return "\n".join(lines)


def format_markdown(metrics: dict) -> str:
    """Format metrics as markdown report."""
    coverage = metrics["metric_2_coverage"]
    infra = metrics["metric_4_infrastructure_review"]

    coverage_status = "On Track" if coverage["status"] == "on_track" else "Behind"
    infra_status = "On Track" if infra["status"] == "on_track" else "Behind"

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
        f"| Agent Coverage | {coverage['coverage_rate']}% | {coverage['target']}% | {coverage_status} |",
        f"| Infrastructure Review | {infra['review_rate']}% | {infra['target']}% | {infra_status} |",
        "",
        "---",
        "",
        "## Metric 1: Invocation Rate by Agent",
        "",
        "| Agent | Invocations | Rate |",
        "|-------|-------------|------|",
    ]

    agents = metrics["metric_1_invocation_rate"]["agents"]
    if agents:
        for agent, data in agents.items():
            lines.append(f"| {agent} | {data['count']} | {data['rate']}% |")
    else:
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
        lines.append(f"| {commit_type} | {data['total']} | {data['with_agent']} | {data['rate']}% |")

    lines.extend([
        "",
        "---",
        "",
        "## Metric 4: Infrastructure Review Rate",
        "",
        f"- **Infrastructure Commits**: {infra['infrastructure_commits']}",
        f"- **With Security Review**: {infra['with_security_review']}",
        f"- **Review Rate**: {infra['review_rate']}%",
        f"- **Target**: {infra['target']}%",
        "",
        "---",
        "",
        "*Generated by collect_metrics.py*",
    ])

    return "\n".join(lines)


def main() -> int:
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Agent Metrics Collection Utility")
    parser.add_argument("--since", type=int, default=30, help="Number of days to analyze")
    parser.add_argument(
        "--output",
        choices=["json", "markdown", "summary"],
        default="summary",
        help="Output format",
    )
    parser.add_argument("--repo-path", default=".", help="Repository path")
    args = parser.parse_args()

    resolved_path = Path(args.repo_path).resolve()
    if not resolved_path.exists():
        print(f"Error: Path not found: {args.repo_path}", file=sys.stderr)
        return 1

    if not (resolved_path / ".git").exists():
        print(f"Error: {resolved_path} is not a git repository", file=sys.stderr)
        return 1

    metrics = get_metrics(str(resolved_path), args.since)

    if args.output == "json":
        print(json.dumps(metrics, indent=2))
    elif args.output == "markdown":
        print(format_markdown(metrics))
    else:
        print(format_summary(metrics))

    return 0


if __name__ == "__main__":
    sys.exit(main())
