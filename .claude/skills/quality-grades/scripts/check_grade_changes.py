#!/usr/bin/env python3
"""Check quality grades for degradation and notify via GitHub issue.

Compares current grades against a degradation threshold and creates
a GitHub issue when domains have critical or degrading grades.

Exit codes:
  0: No degradation detected, or notification sent
  1: Script error
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Check quality grades for degradation and notify")
    parser.add_argument(
        "--grades-file",
        type=Path,
        required=True,
        help="Path to JSON grades file from grade_domains.py",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=60,
        help="Score threshold below which a domain is flagged (default: 60)",
    )
    return parser.parse_args(argv)


def load_grades(path: Path) -> dict:
    """Load grades from JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def find_degraded_domains(data: dict, threshold: int) -> list[dict]:
    """Find domains that are degrading or below the score threshold."""
    flagged = []
    for domain in data.get("domains", []):
        trend = domain.get("trend", "new")
        score = domain.get("overall_score", 100)
        grade = domain.get("overall_grade", "?")

        if trend == "degrading" or score < threshold:
            critical_gaps = sum(
                1
                for layer in domain.get("layers", [])
                for gap in layer.get("gaps", [])
                if gap.get("severity") == "critical"
            )
            flagged.append(
                {
                    "domain": domain["domain"],
                    "grade": grade,
                    "score": score,
                    "trend": trend,
                    "critical_gaps": critical_gaps,
                }
            )
    return flagged


def create_notification_issue(flagged: list[dict]) -> None:
    """Create a GitHub issue to notify about degraded grades."""
    title = f"Quality grade degradation: {len(flagged)} domain(s) need attention"

    lines = [
        "## Quality Grade Alert",
        "",
        "The weekly quality audit detected domains that need attention.",
        "",
        "| Domain | Grade | Score | Trend | Critical Gaps |",
        "|--------|-------|-------|-------|---------------|",
    ]
    for d in flagged:
        row = (
            f"| {d['domain']} | {d['grade']} | {d['score']:.0f}"
            f" | {d['trend']} | {d['critical_gaps']} |"
        )
        lines.append(row)
    lines.extend(
        [
            "",
            "Run the grade_domains.py script for the full report.",
            "",
            "This issue was created automatically by the quality-grades audit workflow.",
        ]
    )
    body = "\n".join(lines)

    try:
        subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--title",
                title,
                "--body",
                body,
                "--label",
                "quality",
            ],
            check=True,
        )
    except FileNotFoundError:
        print("Error: 'gh' CLI not found. Install GitHub CLI to create issues.", file=sys.stderr)
        raise
    except subprocess.CalledProcessError as exc:
        print(f"Error: 'gh issue create' failed with exit code {exc.returncode}", file=sys.stderr)
        raise


def main(argv: list[str] | None = None) -> int:
    """Check grades and notify if degradation detected."""
    args = parse_args(argv)

    if not args.grades_file.exists():
        print(f"Error: grades file not found: {args.grades_file}", file=sys.stderr)
        return 1

    data = load_grades(args.grades_file)
    flagged = find_degraded_domains(data, args.threshold)

    if not flagged:
        print("All domains within acceptable quality thresholds.")
        return 0

    print(f"Found {len(flagged)} domain(s) below threshold or degrading:")
    for d in flagged:
        print(f"  {d['domain']}: {d['grade']} ({d['score']:.0f}/100) [{d['trend']}]")

    try:
        create_notification_issue(flagged)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return 1
    print("Notification issue created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
