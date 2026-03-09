#!/usr/bin/env python3
"""Retrieve agent invocation history from git history.

Queries git commit history to build a timeline of agent invocations.
When Agent Orchestration MCP (agents://history) is available, it will
be the primary source. Until then, this uses heuristic detection from
git commits.

Usage:
    python get_agent_history.py [--lookback-hours 8] [--format json|table]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta

AGENT_PATTERNS: dict[str, list[str]] = {
    "orchestrator": ["orchestrat", "routing", "dispatch"],
    "planner": ["plan", "milestone", "breakdown"],
    "implementer": ["implement", "feat:", "fix:", "refactor:"],
    "qa": ["test:", "qa", "validation", "coverage"],
    "security": ["security", "cwe", "owasp", "vulnerability"],
    "architect": ["architect", "adr", "design"],
    "critic": ["critic", "critique", "blocker"],
    "devops": ["ci:", "cd:", "workflow", "deploy", "devops"],
    "analyst": ["analysis", "research", "rca", "root cause"],
    "explainer": ["docs:", "prd", "documentation", "explainer"],
    "retrospective": ["retrospective", "learning", "retro"],
    "memory": ["memory", "serena", "forgetful"],
    "merge-resolver": ["merge", "conflict", "resolution"],
}


def _run_git(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def get_agent_history(lookback_hours: int) -> list[dict]:
    since = (datetime.now(UTC) - timedelta(hours=lookback_hours)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    lines = _run_git("log", f"--since={since}", "--format=%H|%s|%ai")

    history: list[dict] = []
    order = 1

    for line in lines:
        parts = line.split("|", 2)
        if len(parts) < 2:
            continue

        commit_hash = parts[0][:8]
        message = parts[1]
        timestamp = parts[2] if len(parts) >= 3 else ""
        msg_lower = message.lower()

        detected: set[str] = set()
        for agent, patterns in AGENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(re.escape(pattern), msg_lower):
                    detected.add(agent)
                    break

        for agent in sorted(detected):
            history.append(
                {
                    "Order": order,
                    "Agent": agent,
                    "Commit": commit_hash,
                    "Message": message,
                    "Timestamp": timestamp,
                }
            )
            order += 1

    return history


def main() -> None:
    parser = argparse.ArgumentParser(description="Get agent invocation history")
    parser.add_argument(
        "--lookback-hours", type=int, default=8, help="Hours to look back (default: 8)"
    )
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="json",
        help="Output format (default: json)",
    )
    args = parser.parse_args()

    # Verify we're in a git repo
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if result.returncode != 0:
        print("Error: Not inside a git repository.", file=sys.stderr)
        sys.exit(1)

    history = get_agent_history(args.lookback_hours)

    if args.format == "table":
        if not history:
            print("No agent activity found.")
            return
        print(f"{'Order':<6} {'Agent':<20} {'Commit':<10} {'Message'}")
        print("-" * 80)
        for entry in history:
            print(
                f"{entry['Order']:<6} {entry['Agent']:<20} {entry['Commit']:<10} {entry['Message']}"
            )
    else:
        print(json.dumps(history, indent=2))


if __name__ == "__main__":
    main()
