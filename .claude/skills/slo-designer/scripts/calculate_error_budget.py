#!/usr/bin/env python3
"""Calculate error budget for SLO targets.

This script calculates the error budget (allowed downtime/failures) for a given
SLO target over various time periods.

Exit Codes:
    0: Success
    1: Invalid arguments
    2: Calculation error
"""

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Literal


@dataclass
class ErrorBudget:
    """Error budget calculation result."""

    target_percent: float
    error_budget_percent: float
    period: str
    period_minutes: int
    downtime_minutes: float
    downtime_seconds: float

    def format_downtime(self) -> str:
        """Format downtime as human-readable string."""
        total_seconds = self.downtime_seconds
        if total_seconds < 60:
            return f"{total_seconds:.1f}s"
        elif total_seconds < 3600:
            minutes = int(total_seconds // 60)
            seconds = int(total_seconds % 60)
            return f"{minutes}m {seconds}s"
        else:
            hours = int(total_seconds // 3600)
            remaining = total_seconds % 3600
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            if hours > 0 and minutes > 0:
                return f"{hours}h {minutes}m {seconds}s"
            elif hours > 0:
                return f"{hours}h {seconds}s"
            else:
                return f"{minutes}m {seconds}s"


PERIOD_MINUTES = {
    "daily": 24 * 60,
    "weekly": 7 * 24 * 60,
    "monthly": 30 * 24 * 60,
    "quarterly": 90 * 24 * 60,
    "yearly": 365 * 24 * 60,
}


def calculate_error_budget(
    target: float, period: Literal["daily", "weekly", "monthly", "quarterly", "yearly"]
) -> ErrorBudget:
    """Calculate error budget for a given SLO target.

    Args:
        target: SLO target as a percentage (e.g., 99.9)
        period: Time period for calculation

    Returns:
        ErrorBudget with calculation results

    Raises:
        ValueError: If target is not between 0 and 100
    """
    if not 0 < target <= 100:
        raise ValueError(f"Target must be between 0 and 100, got {target}")

    # Use round to avoid floating point precision issues
    error_budget_percent = round(100 - target, 6)
    period_minutes = PERIOD_MINUTES[period]
    downtime_minutes = (error_budget_percent / 100) * period_minutes
    downtime_seconds = downtime_minutes * 60

    return ErrorBudget(
        target_percent=target,
        error_budget_percent=error_budget_percent,
        period=period,
        period_minutes=period_minutes,
        downtime_minutes=downtime_minutes,
        downtime_seconds=downtime_seconds,
    )


def calculate_burn_rates(error_budget: ErrorBudget) -> dict:
    """Calculate burn rates and time to exhaustion.

    Args:
        error_budget: The error budget to analyze

    Returns:
        Dictionary with burn rate analysis
    """
    budget_minutes = error_budget.downtime_minutes

    burn_rates = {
        "1x": {
            "description": "Normal consumption",
            "hours_to_exhaust": budget_minutes / 60,
            "alert_severity": "Info",
        },
        "2x": {
            "description": "Elevated consumption",
            "hours_to_exhaust": budget_minutes / (2 * 60),
            "alert_severity": "Warning",
        },
        "6x": {
            "description": "High consumption",
            "hours_to_exhaust": budget_minutes / (6 * 60),
            "alert_severity": "Urgent",
        },
        "14.4x": {
            "description": "Critical consumption",
            "hours_to_exhaust": budget_minutes / (14.4 * 60),
            "alert_severity": "Critical",
        },
        "36x": {
            "description": "Emergency consumption",
            "hours_to_exhaust": budget_minutes / (36 * 60),
            "alert_severity": "Emergency",
        },
    }

    return burn_rates


def format_text_output(budget: ErrorBudget, burn_rates: dict) -> str:
    """Format output as plain text."""
    lines = [
        "SLO Error Budget Calculator",
        f"{'=' * 40}",
        "",
        f"Target: {budget.target_percent}%",
        f"Period: {budget.period}",
        "",
        f"Error Budget: {budget.error_budget_percent}%",
        f"Allowed Downtime: {budget.format_downtime()}",
        f"  ({budget.downtime_minutes:.2f} minutes)",
        "",
        "Burn Rate Analysis:",
        f"{'-' * 40}",
    ]

    for rate, data in burn_rates.items():
        hours = data["hours_to_exhaust"]
        if hours < 1:
            time_str = f"{hours * 60:.1f} minutes"
        elif hours < 24:
            time_str = f"{hours:.1f} hours"
        else:
            time_str = f"{hours / 24:.1f} days"

        lines.append(
            f"  {rate:>6} burn: {time_str:>15} to exhaust ({data['alert_severity']})"
        )

    return "\n".join(lines)


def format_json_output(budget: ErrorBudget, burn_rates: dict) -> str:
    """Format output as JSON."""
    result = {
        "target_percent": budget.target_percent,
        "error_budget_percent": budget.error_budget_percent,
        "period": budget.period,
        "period_minutes": budget.period_minutes,
        "downtime_minutes": round(budget.downtime_minutes, 2),
        "downtime_seconds": round(budget.downtime_seconds, 2),
        "downtime_formatted": budget.format_downtime(),
        "burn_rates": {
            rate: {
                "hours_to_exhaust": round(data["hours_to_exhaust"], 2),
                "alert_severity": data["alert_severity"],
            }
            for rate, data in burn_rates.items()
        },
    }
    return json.dumps(result, indent=2)


def format_markdown_output(budget: ErrorBudget, burn_rates: dict) -> str:
    """Format output as Markdown."""
    lines = [
        f"## Error Budget: {budget.target_percent}% SLO ({budget.period})",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| SLO Target | {budget.target_percent}% |",
        f"| Error Budget | {budget.error_budget_percent}% |",
        f"| Allowed Downtime | {budget.format_downtime()} |",
        f"| Period | {budget.period} ({budget.period_minutes} minutes) |",
        "",
        "### Burn Rate Analysis",
        "",
        "| Burn Rate | Time to Exhaust | Alert Severity |",
        "|-----------|-----------------|----------------|",
    ]

    for rate, data in burn_rates.items():
        hours = data["hours_to_exhaust"]
        if hours < 1:
            time_str = f"{hours * 60:.1f} minutes"
        elif hours < 24:
            time_str = f"{hours:.1f} hours"
        else:
            time_str = f"{hours / 24:.1f} days"

        lines.append(f"| {rate} | {time_str} | {data['alert_severity']} |")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Calculate error budget for SLO targets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --target 99.9
  %(prog)s --target 99.9 --period weekly
  %(prog)s --target 99.95 --period monthly --format json
  %(prog)s --target 99.99 --format markdown

Common SLO Targets:
  99%    - 7h 18m downtime/month (internal services)
  99.5%  - 3h 39m downtime/month (standard APIs)
  99.9%  - 43m downtime/month (production services)
  99.95% - 22m downtime/month (critical services)
  99.99% - 4m downtime/month (high availability)
        """,
    )

    parser.add_argument(
        "--target",
        type=float,
        required=True,
        help="SLO target percentage (e.g., 99.9)",
    )

    parser.add_argument(
        "--period",
        choices=["daily", "weekly", "monthly", "quarterly", "yearly"],
        default="monthly",
        help="Time period for calculation (default: monthly)",
    )

    parser.add_argument(
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text)",
    )

    args = parser.parse_args()

    try:
        budget = calculate_error_budget(args.target, args.period)
        burn_rates = calculate_burn_rates(budget)

        if args.format == "json":
            print(format_json_output(budget, burn_rates))
        elif args.format == "markdown":
            print(format_markdown_output(budget, burn_rates))
        else:
            print(format_text_output(budget, burn_rates))

        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Calculation error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
