#!/usr/bin/env python3
"""Validate a threat model document for completeness.

Checks that a threat model has all required sections, valid STRIDE
categories, and proper risk ratings.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


def validate_path_no_traversal(path: Path, context: str = "path") -> Path:
    """Validate that path does not contain traversal patterns (CWE-22 protection).

    This prevents directory traversal attacks like '../../../etc/passwd' while
    still allowing legitimate absolute paths and paths within the working directory.
    """
    # Check for traversal patterns in the path string
    path_str = str(path)
    if ".." in path_str:
        raise PermissionError(
            f"Path traversal attempt detected: '{path}' contains prohibited '..' sequence."
        )

    # Resolve the path and check it doesn't escape when resolved
    resolved = path.resolve()

    # If original path was relative, ensure resolved doesn't escape cwd
    if not path.is_absolute():
        try:
            resolved.relative_to(Path.cwd().resolve())
        except ValueError as e:
            raise PermissionError(
                f"Path traversal attempt detected: '{path}' resolves outside the working directory."
            ) from e

    return resolved


@dataclass
class ValidationResult:
    """Result of validation check."""

    passed: bool
    message: str
    severity: str = "error"  # error, warning, info


REQUIRED_SECTIONS = [
    ("Scope", r"##\s+\d*\.?\s*Scope"),
    ("Architecture Overview", r"##\s+\d*\.?\s*Architecture"),
    ("STRIDE Analysis", r"##\s+\d*\.?\s*STRIDE"),
    ("Threat Matrix", r"##\s+\d*\.?\s*Threat\s+Matrix"),
    ("Mitigations", r"##\s+\d*\.?\s*Mitigations"),
]

STRIDE_CATEGORIES = {"S", "T", "R", "I", "D", "E"}

RISK_LEVELS = {"Critical", "High", "Medium", "Low"}


def check_required_sections(content: str) -> list[ValidationResult]:
    """Check that all required sections are present.

    Args:
        content: Markdown content

    Returns:
        List of validation results
    """
    results = []

    for name, pattern in REQUIRED_SECTIONS:
        if re.search(pattern, content, re.IGNORECASE):
            results.append(ValidationResult(
                passed=True,
                message=f"Section '{name}' present",
                severity="info"
            ))
        else:
            results.append(ValidationResult(
                passed=False,
                message=f"Missing required section: {name}",
                severity="error"
            ))

    return results


def check_threat_matrix(content: str) -> list[ValidationResult]:
    """Validate threat matrix table.

    Args:
        content: Markdown content

    Returns:
        List of validation results
    """
    results = []

    # Find threat matrix
    table_pattern = r'\| ID \| Element \| STRIDE \| Threat \|.*?\n((?:\|.*\n)*)'
    match = re.search(table_pattern, content, re.IGNORECASE)

    if not match:
        results.append(ValidationResult(
            passed=False,
            message="Threat matrix table not found or has invalid header",
            severity="error"
        ))
        return results

    table_rows = match.group(1).strip().split('\n')
    threat_count = 0
    stride_found = set()
    risk_found = set()

    for row in table_rows:
        if '---' in row:
            continue

        cells = [c.strip() for c in row.split('|')[1:-1]]
        if len(cells) < 7:
            continue

        threat_count += 1
        threat_id = cells[0]
        stride = cells[2].upper()
        risk = cells[6]

        # Validate STRIDE category
        if stride in STRIDE_CATEGORIES:
            stride_found.add(stride)
        else:
            results.append(ValidationResult(
                passed=False,
                message=f"{threat_id}: Invalid STRIDE category '{stride}'",
                severity="error"
            ))

        # Validate risk level
        risk_valid = False
        for level in RISK_LEVELS:
            if level.lower() in risk.lower():
                risk_found.add(level)
                risk_valid = True
                break

        if not risk_valid:
            results.append(ValidationResult(
                passed=False,
                message=f"{threat_id}: Invalid risk level '{risk}'",
                severity="error"
            ))

    # Summary checks
    if threat_count == 0:
        results.append(ValidationResult(
            passed=False,
            message="No threats found in threat matrix",
            severity="error"
        ))
    else:
        results.append(ValidationResult(
            passed=True,
            message=f"Found {threat_count} threats",
            severity="info"
        ))

    # Check STRIDE coverage
    missing_stride = STRIDE_CATEGORIES - stride_found
    if missing_stride:
        results.append(ValidationResult(
            passed=True,  # Warning, not error
            message=f"STRIDE categories not addressed: {', '.join(sorted(missing_stride))}",
            severity="warning"
        ))
    else:
        results.append(ValidationResult(
            passed=True,
            message="All STRIDE categories addressed",
            severity="info"
        ))

    return results


def check_mitigations(content: str) -> list[ValidationResult]:
    """Check that high-priority threats have mitigations.

    Args:
        content: Markdown content

    Returns:
        List of validation results
    """
    results = []

    # Find Critical/High threats - deduplicate
    threat_pattern = r'\| (T\d+) \|.*?\| (Critical|High) \|'
    all_matches = re.findall(threat_pattern, content, re.IGNORECASE)
    # Deduplicate by threat ID, keeping first occurrence
    seen = set()
    critical_high = []
    for threat_id, risk in all_matches:
        if threat_id not in seen:
            seen.add(threat_id)
            critical_high.append((threat_id, risk))

    if not critical_high:
        results.append(ValidationResult(
            passed=True,
            message="No Critical/High threats (or already mitigated)",
            severity="info"
        ))
        return results

    # Check mitigations section - capture until next level-2 heading or end
    mitigations_section = re.search(
        r'##\s+\d*\.?\s*Mitigations(.*?)(?=\n##\s+\d|$)',
        content,
        re.IGNORECASE | re.DOTALL
    )

    if not mitigations_section:
        results.append(ValidationResult(
            passed=False,
            message="Mitigations section missing",
            severity="error"
        ))
        return results

    mitigation_content = mitigations_section.group(1)

    for threat_id, risk in critical_high:
        if threat_id.lower() in mitigation_content.lower():
            results.append(ValidationResult(
                passed=True,
                message=f"{threat_id} ({risk}): Mitigation documented",
                severity="info"
            ))
        else:
            results.append(ValidationResult(
                passed=False,
                message=f"{threat_id} ({risk}): No mitigation found",
                severity="error"
            ))

    return results


def check_components(content: str) -> list[ValidationResult]:
    """Check that components are defined.

    Args:
        content: Markdown content

    Returns:
        List of validation results
    """
    results = []

    # Look for components table
    components_pattern = r'\| ID \| Name \| Type \| Description \|.*?\n((?:\|.*\n)*)'
    match = re.search(components_pattern, content, re.IGNORECASE)

    if not match:
        results.append(ValidationResult(
            passed=True,  # Warning, not error
            message="Components table not found (optional)",
            severity="warning"
        ))
        return results

    rows = [r for r in match.group(1).strip().split('\n') if '---' not in r]
    component_count = len(rows)

    if component_count == 0:
        results.append(ValidationResult(
            passed=False,
            message="Components table is empty",
            severity="warning"
        ))
    else:
        results.append(ValidationResult(
            passed=True,
            message=f"Found {component_count} components",
            severity="info"
        ))

    return results


def validate_threat_model(path: Path) -> tuple[bool, list[ValidationResult]]:
    """Validate a threat model document.

    Args:
        path: Path to threat model markdown

    Returns:
        Tuple of (overall_pass, results)
    """
    # Validate path to prevent traversal (CWE-22)
    try:
        validate_path_no_traversal(path, "document path")
    except PermissionError as e:
        return False, [ValidationResult(
            passed=False,
            message=str(e),
            severity="error"
        )]

    if not path.exists():
        return False, [ValidationResult(
            passed=False,
            message=f"File not found: {path}",
            severity="error"
        )]

    content = path.read_text()
    results = []

    # Run all checks
    results.extend(check_required_sections(content))
    results.extend(check_threat_matrix(content))
    results.extend(check_mitigations(content))
    results.extend(check_components(content))

    # Calculate overall pass
    errors = [r for r in results if not r.passed and r.severity == "error"]
    overall_pass = len(errors) == 0

    return overall_pass, results


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate a threat model document for completeness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python validate_threat_model.py auth-threats.md
  python validate_threat_model.py .agents/security/threat-models/payment.md
        """,
    )

    parser.add_argument(
        "path",
        type=Path,
        help="Path to the threat model markdown file",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    passed, results = validate_threat_model(args.path)

    if args.json:
        import json
        output = {
            "passed": passed,
            "results": [
                {"passed": r.passed, "message": r.message, "severity": r.severity}
                for r in results
            ]
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Validating: {args.path}")
        print("=" * 60)

        errors = []
        warnings = []
        info = []

        for r in results:
            if r.severity == "error":
                errors.append(r)
            elif r.severity == "warning":
                warnings.append(r)
            else:
                info.append(r)

        if errors:
            print("\nERRORS:")
            for r in errors:
                status = "PASS" if r.passed else "FAIL"
                print(f"  [{status}] {r.message}")

        if warnings:
            print("\nWARNINGS:")
            for r in warnings:
                print(f"  [WARN] {r.message}")

        if info:
            print("\nINFO:")
            for r in info:
                print(f"  [INFO] {r.message}")

        print("=" * 60)
        if passed:
            print("RESULT: PASSED")
        else:
            print(f"RESULT: FAILED ({len(errors)} errors)")

    return 0 if passed else 10


if __name__ == "__main__":
    sys.exit(main())
