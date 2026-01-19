#!/usr/bin/env python3
"""
Validate a chaos experiment document for completeness.

Usage:
    python validate_experiment.py path/to/experiment.md
    python validate_experiment.py path/to/experiment.md --strict
    python validate_experiment.py --help

Exit Codes:
    0  - Validation passed
    1  - General failure
    2  - Invalid arguments
    10 - Validation failure (missing required sections)
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ValidationResult:
    """Structured validation result."""

    success: bool
    message: str
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    score: int = 0  # 0-100


# Required sections that must be present and filled out
REQUIRED_SECTIONS = [
    ("Metadata", r"## Metadata"),
    ("System Under Test", r"## System Under Test"),
    ("Steady State Baseline", r"## Steady State Baseline"),
    ("Hypothesis", r"## Hypothesis"),
    ("Injection Plan", r"## Injection Plan"),
    ("Rollback Procedure", r"## Rollback Procedure"),
]

# Sections that should be present for a complete experiment
RECOMMENDED_SECTIONS = [
    ("Business Justification", r"## Business Justification"),
    ("Approvals", r"## Approvals"),
    ("Execution Log", r"## Execution Log"),
    ("Results", r"## Results"),
]

# Patterns that indicate incomplete content
INCOMPLETE_PATTERNS = [
    (r"\{\{[A-Z_]+\}\}", "Template placeholder found"),
    (r"TBD(?!\s*\|)", "TBD marker found"),
    (r"TODO", "TODO marker found"),
    (r"\[FILL IN\]", "Fill-in marker found"),
]


def load_document(path: Path) -> str:
    """Load the experiment document."""
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")
    if not path.suffix.lower() == ".md":
        raise ValueError(f"Expected .md file, got: {path.suffix}")
    return path.read_text(encoding="utf-8")


def check_section_presence(content: str, sections: list) -> tuple[list, list]:
    """Check which sections are present and which are missing."""
    present = []
    missing = []

    for name, pattern in sections:
        if re.search(pattern, content, re.IGNORECASE):
            present.append(name)
        else:
            missing.append(name)

    return present, missing


def check_incomplete_markers(content: str) -> list:
    """Find incomplete content markers."""
    issues = []

    for pattern, description in INCOMPLETE_PATTERNS:
        matches = re.findall(pattern, content)
        if matches:
            # Count unique matches
            unique_matches = set(matches)
            for match in unique_matches:
                count = matches.count(match)
                issues.append(f"{description}: '{match}' ({count} occurrence(s))")

    return issues


def check_hypothesis_quality(content: str) -> tuple[bool, list]:
    """Check if hypothesis follows the proper format."""
    warnings = []

    # Look for hypothesis section
    hypothesis_match = re.search(
        r"## Hypothesis\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )

    if not hypothesis_match:
        return False, ["Hypothesis section not found"]

    hypothesis_text = hypothesis_match.group(1)

    # Check for key hypothesis components
    has_given = "given" in hypothesis_text.lower()
    has_when = "when" in hypothesis_text.lower()
    has_then = "then" in hypothesis_text.lower()
    has_because = "because" in hypothesis_text.lower()

    if not has_given:
        warnings.append("Hypothesis missing 'Given' clause (steady state)")
    if not has_when:
        warnings.append("Hypothesis missing 'When' clause (failure injection)")
    if not has_then:
        warnings.append("Hypothesis missing 'Then' clause (expected behavior)")
    if not has_because:
        warnings.append("Hypothesis missing 'Because' clause (resilience mechanism)")

    is_complete = has_given and has_when and has_then and has_because
    return is_complete, warnings


def check_rollback_procedure(content: str) -> tuple[bool, list]:
    """Check if rollback procedure is documented."""
    warnings = []

    rollback_match = re.search(
        r"## Rollback Procedure\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )

    if not rollback_match:
        return False, ["Rollback Procedure section not found"]

    rollback_text = rollback_match.group(1)

    # Check for code blocks (commands)
    has_commands = "```" in rollback_text
    if not has_commands:
        warnings.append("Rollback procedure should include executable commands")

    # Check for verification steps
    has_verification = (
        "verify" in rollback_text.lower() or "verification" in rollback_text.lower()
    )
    if not has_verification:
        warnings.append("Rollback procedure should include verification steps")

    return len(warnings) == 0, warnings


def check_metrics_defined(content: str) -> tuple[bool, list]:
    """Check if baseline metrics are defined."""
    warnings = []

    baseline_match = re.search(
        r"## Steady State Baseline\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )

    if not baseline_match:
        return False, ["Steady State Baseline section not found"]

    baseline_text = baseline_match.group(1)

    # Check for metric tables
    has_table = "|" in baseline_text and "Metric" in baseline_text
    if not has_table:
        warnings.append("Baseline should include a metrics table")

    # Check for threshold definitions
    has_thresholds = (
        "threshold" in baseline_text.lower() or "green" in baseline_text.lower()
    )
    if not has_thresholds:
        warnings.append("Baseline should define tolerance thresholds")

    return len(warnings) == 0, warnings


def calculate_score(
    required_present: int,
    required_total: int,
    recommended_present: int,
    recommended_total: int,
    incomplete_count: int,
    hypothesis_complete: bool,
    rollback_complete: bool,
    metrics_complete: bool,
) -> int:
    """Calculate a completeness score (0-100)."""
    # Required sections: 40 points
    required_score = (required_present / required_total) * 40 if required_total else 40

    # Recommended sections: 20 points
    recommended_score = (
        (recommended_present / recommended_total) * 20 if recommended_total else 20
    )

    # No incomplete markers: 20 points
    incomplete_score = max(0, 20 - (incomplete_count * 2))

    # Quality checks: 20 points
    quality_score = 0
    if hypothesis_complete:
        quality_score += 8
    if rollback_complete:
        quality_score += 6
    if metrics_complete:
        quality_score += 6

    total = required_score + recommended_score + incomplete_score + quality_score
    return min(100, max(0, int(total)))


def validate_experiment(path: Path, strict: bool = False) -> ValidationResult:
    """Validate an experiment document."""
    errors = []
    warnings = []

    try:
        content = load_document(path)
    except FileNotFoundError as e:
        return ValidationResult(
            success=False,
            message=str(e),
            errors=[str(e)],
            score=0,
        )
    except ValueError as e:
        return ValidationResult(
            success=False,
            message=str(e),
            errors=[str(e)],
            score=0,
        )

    # Check required sections
    required_present, required_missing = check_section_presence(
        content, REQUIRED_SECTIONS
    )
    for section in required_missing:
        errors.append(f"Missing required section: {section}")

    # Check recommended sections
    recommended_present, recommended_missing = check_section_presence(
        content, RECOMMENDED_SECTIONS
    )
    for section in recommended_missing:
        warnings.append(f"Missing recommended section: {section}")

    # Check for incomplete markers
    incomplete_issues = check_incomplete_markers(content)
    if strict:
        errors.extend(incomplete_issues)
    else:
        warnings.extend(incomplete_issues)

    # Quality checks
    hypothesis_complete, hypothesis_warnings = check_hypothesis_quality(content)
    warnings.extend(hypothesis_warnings)

    rollback_complete, rollback_warnings = check_rollback_procedure(content)
    warnings.extend(rollback_warnings)

    metrics_complete, metrics_warnings = check_metrics_defined(content)
    warnings.extend(metrics_warnings)

    # Calculate score
    score = calculate_score(
        required_present=len(required_present),
        required_total=len(REQUIRED_SECTIONS),
        recommended_present=len(recommended_present),
        recommended_total=len(RECOMMENDED_SECTIONS),
        incomplete_count=len(incomplete_issues),
        hypothesis_complete=hypothesis_complete,
        rollback_complete=rollback_complete,
        metrics_complete=metrics_complete,
    )

    # Determine success
    success = len(errors) == 0

    if success:
        message = f"Validation passed (score: {score}/100)"
    else:
        message = f"Validation failed with {len(errors)} error(s) (score: {score}/100)"

    return ValidationResult(
        success=success,
        message=message,
        errors=errors,
        warnings=warnings,
        score=score,
    )


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate a chaos experiment document",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python validate_experiment.py experiment.md
    python validate_experiment.py experiment.md --strict
    python validate_experiment.py .agents/chaos/*.md --json

Exit Codes:
    0  - Validation passed
    1  - General failure
    2  - Invalid arguments
    10 - Validation failure
        """,
    )

    parser.add_argument(
        "path",
        type=Path,
        help="Path to the experiment document",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat incomplete markers as errors",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )

    args = parser.parse_args()

    result = validate_experiment(args.path, strict=args.strict)

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "success": result.success,
                    "message": result.message,
                    "score": result.score,
                    "errors": result.errors,
                    "warnings": result.warnings,
                }
            )
        )
    else:
        # Human-readable output
        print(f"{'PASS' if result.success else 'FAIL'}: {result.message}")
        print()

        if result.errors:
            print("Errors:")
            for error in result.errors:
                print(f"  - {error}")
            print()

        if result.warnings:
            print("Warnings:")
            for warning in result.warnings:
                print(f"  - {warning}")
            print()

        print(f"Completeness Score: {result.score}/100")

    # Return appropriate exit code
    if result.success:
        return 0
    elif result.errors:
        return 10  # Validation failure
    else:
        return 1  # General failure


if __name__ == "__main__":
    sys.exit(main())
