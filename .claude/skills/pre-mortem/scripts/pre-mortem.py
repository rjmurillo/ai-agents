#!/usr/bin/env python3
"""
Pre-Mortem Risk Inventory Validator

Validates that a risk inventory document contains all required sections
and calculates aggregate risk statistics.

Exit Codes:
    0: Valid inventory with all required fields
    1: Invalid arguments or file not found
    10: Validation failed (missing required sections)
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ValidationResult:
    """Result of validation operation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    statistics: dict = field(default_factory=dict)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.valid = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


@dataclass
class Risk:
    """Represents a single risk entry."""

    id: str
    name: str
    category: str
    likelihood: int
    impact: int
    score: int
    has_mitigation: bool
    owner: Optional[str] = None
    status: Optional[str] = None


REQUIRED_SECTIONS = [
    "Project Context",
    "Risk Summary",
    "Critical Risks",
    "High Risks",
    "Medium Risks",
    "Low Risks",
    "Action Items",
]

VALID_CATEGORIES = [
    "Technical",
    "People",
    "Process",
    "Organizational",
    "External",
    "Unknown",
]

VALID_STATUSES = ["Open", "Mitigating", "Accepted", "Resolved"]


def parse_risk_entry(text: str) -> Optional[Risk]:
    """Parse a risk entry from markdown text."""
    # Extract risk ID and name from header
    header_match = re.search(r"###\s+R(\d+):\s+(.+)", text)
    if not header_match:
        return None

    risk_id = f"R{header_match.group(1)}"
    name = header_match.group(2).strip()

    # Extract category
    category_match = re.search(r"\*\*Category:\*\*\s*(.+)", text)
    category = category_match.group(1).strip() if category_match else "Unknown"

    # Extract likelihood
    likelihood_match = re.search(r"\*\*Likelihood:\*\*\s*(\d+)", text)
    likelihood = int(likelihood_match.group(1)) if likelihood_match else 0

    # Extract impact
    impact_match = re.search(r"\*\*Impact:\*\*\s*(\d+)", text)
    impact = int(impact_match.group(1)) if impact_match else 0

    # Extract score
    score_match = re.search(r"\*\*Score:\*\*\s*(\d+)", text)
    if score_match:
        score = int(score_match.group(1))
    else:
        score = likelihood * impact

    # Check for mitigation section
    has_mitigation = "**Mitigation:**" in text or "**Prevention:**" in text

    # Extract owner
    owner_match = re.search(r"\*\*Owner:\*\*\s*(.+)", text)
    owner = owner_match.group(1).strip() if owner_match else None

    # Extract status
    status_match = re.search(r"\*\*Status:\*\*\s*(.+)", text)
    status = status_match.group(1).strip() if status_match else None

    return Risk(
        id=risk_id,
        name=name,
        category=category,
        likelihood=likelihood,
        impact=impact,
        score=score,
        has_mitigation=has_mitigation,
        owner=owner,
        status=status,
    )


def validate_inventory(content: str) -> ValidationResult:
    """Validate a risk inventory document."""
    result = ValidationResult(valid=True)

    # Check required sections
    for section in REQUIRED_SECTIONS:
        pattern = rf"##\s+{re.escape(section)}"
        if not re.search(pattern, content, re.IGNORECASE):
            result.add_error(f"Missing required section: {section}")

    # Check project context fields
    if "**Project:**" not in content and "**Objective:**" not in content:
        result.add_error("Project context missing: no project name or objective found")

    if "**Date:**" not in content:
        result.add_warning("Missing date field in header")

    # Parse risks
    risks: list[Risk] = []

    # Find all risk entries (### R[N]: ...)
    risk_pattern = r"###\s+R\d+:.+?(?=###\s+R\d+:|##\s+|$)"
    risk_matches = re.findall(risk_pattern, content, re.DOTALL)

    for match in risk_matches:
        risk = parse_risk_entry(match)
        if risk:
            risks.append(risk)

    # Validate individual risks
    for risk in risks:
        # Validate score range based on section
        if risk.score >= 15 and "Critical" not in content:
            result.add_warning(f"{risk.id} has critical score but may be misplaced")

        # Check for mitigation on high-priority risks
        if risk.score >= 8 and not risk.has_mitigation:
            result.add_error(f"{risk.id} (score {risk.score}) missing mitigation plan")

        # Validate likelihood and impact ranges
        if risk.likelihood < 1 or risk.likelihood > 5:
            result.add_error(f"{risk.id} has invalid likelihood: {risk.likelihood}")

        if risk.impact < 1 or risk.impact > 5:
            result.add_error(f"{risk.id} has invalid impact: {risk.impact}")

        # Validate score calculation
        expected_score = risk.likelihood * risk.impact
        if risk.score != expected_score:
            result.add_warning(
                f"{risk.id} score mismatch: {risk.score} != {risk.likelihood} x {risk.impact}"
            )

    # Check for action items
    action_pattern = r"\|\s*A\d+\s*\|"
    if not re.search(action_pattern, content):
        if any(r.score >= 8 for r in risks):
            result.add_warning("No action items defined for high-priority risks")

    # Calculate statistics
    result.statistics = {
        "total_risks": len(risks),
        "critical_count": sum(1 for r in risks if r.score >= 15),
        "high_count": sum(1 for r in risks if 8 <= r.score < 15),
        "medium_count": sum(1 for r in risks if 4 <= r.score < 8),
        "low_count": sum(1 for r in risks if r.score < 4),
        "average_score": sum(r.score for r in risks) / len(risks) if risks else 0,
        "risks_with_mitigation": sum(1 for r in risks if r.has_mitigation),
        "risks_with_owner": sum(1 for r in risks if r.owner),
    }

    return result


def print_result(result: ValidationResult) -> None:
    """Print validation result to stdout."""
    print("\n" + "=" * 60)
    print("PRE-MORTEM RISK INVENTORY VALIDATION")
    print("=" * 60)

    # Status
    status = "VALID" if result.valid else "INVALID"
    print(f"\nStatus: {status}")

    # Errors
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors:
            print(f"  [ERROR] {error}")

    # Warnings
    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for warning in result.warnings:
            print(f"  [WARN] {warning}")

    # Statistics
    if result.statistics:
        print("\nRisk Statistics:")
        print(f"  Total Risks: {result.statistics['total_risks']}")
        print(f"  Critical (15-25): {result.statistics['critical_count']}")
        print(f"  High (8-14): {result.statistics['high_count']}")
        print(f"  Medium (4-7): {result.statistics['medium_count']}")
        print(f"  Low (1-3): {result.statistics['low_count']}")
        print(f"  Average Score: {result.statistics['average_score']:.1f}")
        print(f"  With Mitigation: {result.statistics['risks_with_mitigation']}")
        print(f"  With Owner: {result.statistics['risks_with_owner']}")

    print("\n" + "=" * 60)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate a pre-mortem risk inventory document"
    )
    parser.add_argument(
        "--inventory-path",
        type=str,
        required=True,
        help="Path to the risk inventory markdown file",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run validation (default behavior)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output, only return exit code",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )

    args = parser.parse_args()

    # Check file exists
    inventory_path = Path(args.inventory_path)
    if not inventory_path.exists():
        if not args.quiet:
            print(f"Error: File not found: {inventory_path}", file=sys.stderr)
        return 1

    # Read and validate
    try:
        content = inventory_path.read_text(encoding="utf-8")
    except Exception as e:
        if not args.quiet:
            print(f"Error reading file: {e}", file=sys.stderr)
        return 1

    result = validate_inventory(content)

    # Output
    if args.json:
        import json

        output = {
            "valid": result.valid,
            "errors": result.errors,
            "warnings": result.warnings,
            "statistics": result.statistics,
        }
        print(json.dumps(output, indent=2))
    elif not args.quiet:
        print_result(result)

    # Return appropriate exit code
    if not result.valid:
        return 10
    return 0


if __name__ == "__main__":
    sys.exit(main())
