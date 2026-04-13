#!/usr/bin/env python3
"""Validate consistency across planning artifacts.

Scans planning artifacts in .agents/planning/ for cross-document consistency:
  - Effort estimate divergence between epic/PRD and task breakdowns
  - Orphan conditions (specialist conditions without task assignments)

EXIT CODES:
  0  - Success: No issues, or issues found without fail flags
  1  - Error: Issues found with --fail-on-error or --fail-on-warning

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Estimate:
    """An effort estimate extracted from text."""

    low: float
    high: float

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2.0


@dataclass
class ConsistencyResult:
    """Result of comparing two estimates."""

    consistent: bool
    divergence: float
    message: str


@dataclass
class PlanningDocs:
    """Collection of planning documents found for a feature."""

    epic: Path | None = None
    prd: Path | None = None
    tasks: Path | None = None
    plan: Path | None = None
    all_docs: list[Path] = field(default_factory=list)


@dataclass
class ValidationSummary:
    """Accumulated errors and warnings from validation."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


RANGE_ESTIMATE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)"
)
SINGLE_ESTIMATE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b"
)

CONDITION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"QA:\s*(.+)"),
    re.compile(r"Security:\s*(.+)"),
    re.compile(r"DevOps:\s*(.+)"),
    re.compile(r"Architect:\s*(.+)"),
    re.compile(r"Implementer:\s*(.+)"),
]


def extract_estimate(content: str) -> Estimate | None:
    """Extract effort estimates from text content.

    Looks for patterns like "X-Y hours", "Xh", "X hours".
    """
    match = RANGE_ESTIMATE_PATTERN.search(content)
    if match:
        return Estimate(low=float(match.group(1)), high=float(match.group(2)))

    match = SINGLE_ESTIMATE_PATTERN.search(content)
    if match:
        value = float(match.group(1))
        return Estimate(low=value, high=value)

    return None


def find_orphan_conditions(content: str) -> list[str]:
    """Find conditions that are not linked to tasks in tables."""
    orphans: list[str] = []
    lines = content.split("\n")
    in_table = False
    conditions: list[dict[str, str]] = []

    for line in lines:
        if re.match(r"^\s*\|", line):
            in_table = True
        elif re.match(r"^\s*$", line) or line.startswith("#"):
            in_table = False

        if not in_table and re.match(r"^\s*[-*]\s*", line):
            for pattern in CONDITION_PATTERNS:
                match = pattern.search(line)
                if match:
                    conditions.append({
                        "line": line.strip(),
                        "condition": match.group(1).strip(),
                    })

    for cond in conditions:
        escaped = re.escape(cond["condition"])
        table_pattern = re.compile(r"\|\s*[^|]*" + escaped + r"[^|]*\s*\|")
        if not table_pattern.search(content):
            orphans.append(cond["line"])

    return orphans


def check_estimate_consistency(
    source: Estimate | None,
    derived: Estimate | None,
    threshold: int,
) -> ConsistencyResult:
    """Compare estimates between documents."""
    if source is None or derived is None:
        return ConsistencyResult(
            consistent=True,
            divergence=0.0,
            message="Unable to compare estimates",
        )

    if source.midpoint == 0:
        return ConsistencyResult(
            consistent=True,
            divergence=0.0,
            message="Source estimate is zero",
        )

    divergence = abs((derived.midpoint - source.midpoint) / source.midpoint * 100)

    return ConsistencyResult(
        consistent=divergence <= threshold,
        divergence=round(divergence, 1),
        message=(
            f"Source: {source.low}-{source.high}h, "
            f"Derived: {derived.low}-{derived.high}h"
        ),
    )


def find_planning_documents(root: Path, feature: str) -> PlanningDocs | None:
    """Find planning documents for a feature under .agents/planning/."""
    planning_path = root / ".agents" / "planning"
    if not planning_path.is_dir():
        return None

    docs = PlanningDocs()
    files = sorted(planning_path.glob("*.md"))

    for filepath in files:
        docs.all_docs.append(filepath)
        name_lower = filepath.stem.lower()

        if feature:
            feature_lower = feature.lower()
            if re.search(f"epic.*{re.escape(feature_lower)}", name_lower) or re.search(
                f"{re.escape(feature_lower)}.*epic", name_lower
            ):
                docs.epic = filepath
            if re.search(f"prd.*{re.escape(feature_lower)}", name_lower) or re.search(
                f"{re.escape(feature_lower)}.*prd", name_lower
            ):
                docs.prd = filepath
            if re.search(f"task.*{re.escape(feature_lower)}", name_lower) or re.search(
                f"{re.escape(feature_lower)}.*task", name_lower
            ):
                docs.tasks = filepath
            if re.search(f"plan.*{re.escape(feature_lower)}", name_lower) or re.search(
                f"{re.escape(feature_lower)}.*plan", name_lower
            ):
                docs.plan = filepath
        else:
            if re.match(r"^epic", name_lower) and docs.epic is None:
                docs.epic = filepath
            if re.match(r"^prd", name_lower) and docs.prd is None:
                docs.prd = filepath
            if re.match(r"^task", name_lower) and docs.tasks is None:
                docs.tasks = filepath
            if re.match(r"^plan", name_lower) and docs.plan is None:
                docs.plan = filepath

    if docs.plan is None and docs.tasks is None and docs.all_docs:
        docs.plan = docs.all_docs[0]

    return docs


def validate_estimates(
    docs: PlanningDocs,
    threshold: int,
    summary: ValidationSummary,
) -> None:
    """Validate estimate consistency between source and derived documents."""
    print("--- Estimate Consistency Check ---")

    source_doc = docs.epic or docs.prd or docs.plan
    derived_doc = docs.tasks

    if not (source_doc and derived_doc):
        print("Skipping estimate check: source or derived document not found")
        return

    print(f"Comparing: {source_doc.name} -> {derived_doc.name}")

    source_content = source_doc.read_text(encoding="utf-8")
    derived_content = derived_doc.read_text(encoding="utf-8")

    source_est = extract_estimate(source_content)
    derived_est = extract_estimate(derived_content)

    result = check_estimate_consistency(source_est, derived_est, threshold)

    if result.consistent:
        print(f"[PASS] Effort Estimates - Divergence: {result.divergence}%")
    else:
        print(
            f"[WARN] Effort Estimates - Divergence: {result.divergence}% "
            f"(threshold: {threshold}%)"
        )
        print(f"  {result.message}")
        summary.warnings.append(
            f"Estimate divergence of {result.divergence}% exceeds {threshold}% threshold"
        )


def validate_conditions(
    docs: PlanningDocs,
    summary: ValidationSummary,
) -> None:
    """Validate that all conditions are linked to tasks."""
    print("--- Condition Traceability Check ---")

    plan_doc = docs.plan or docs.tasks
    if not plan_doc:
        print("Skipping condition check: no plan document found")
        return

    print(f"Checking: {plan_doc.name}")

    content = plan_doc.read_text(encoding="utf-8")
    orphans = find_orphan_conditions(content)

    if not orphans:
        print("[PASS] Condition Traceability - No orphan conditions")
    else:
        print(f"[FAIL] Condition Traceability - {len(orphans)} orphan condition(s) found")
        for orphan in orphans:
            print(f"  - {orphan}")
        summary.errors.append(f"Orphan conditions found: {'; '.join(orphans)}")


def validate_document_structure(docs: PlanningDocs) -> None:
    """Check all documents for structural issues."""
    print("--- Document Structure Check ---")

    has_estimate_re = re.compile(r"\d+\s*-\s*\d+\s*(?:hours?|hrs?)")
    has_reconciliation_re = re.compile(r"(?i)## Estimate Reconciliation")

    for doc in docs.all_docs:
        try:
            content = doc.read_text(encoding="utf-8")
        except OSError:
            continue
        if not content:
            continue

        if has_estimate_re.search(content) and not has_reconciliation_re.search(content):
            print(
                f"  {doc.name}: Contains estimates but no reconciliation section "
                "(consider adding)"
            )


def print_summary(summary: ValidationSummary) -> None:
    """Print the validation summary."""
    print()
    print("=== Validation Summary ===")
    print()

    if not summary.errors and not summary.warnings:
        print("SUCCESS: All validations passed")
        return

    if summary.warnings:
        print(f"WARNINGS: {len(summary.warnings)}")
        for warning in summary.warnings:
            print(f"  - {warning}")

    if summary.errors:
        print(f"ERRORS: {len(summary.errors)}")
        for err in summary.errors:
            print(f"  - {err}", file=sys.stderr)

    print()
    print("=== Remediation Steps ===")
    print()

    if summary.warnings:
        print("For estimate divergence:")
        print("  1. Add '## Estimate Reconciliation' section to task breakdown")
        print("  2. Document source estimate, derived estimate, and divergence percentage")
        print("  3. Choose action: Update source, Document rationale, or Flag for review")
        print()

    if summary.errors:
        print("For orphan conditions:")
        print("  1. Add 'Conditions' column to Work Breakdown table")
        print("  2. Link each specialist condition to a specific task")
        print("  3. Use format: 'QA: condition text' or 'Security: condition text'")
        print()


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Validate consistency across planning artifacts.",
    )
    parser.add_argument(
        "--feature-name",
        default="",
        help="Name of the feature to validate (default: all features)",
    )
    parser.add_argument(
        "--path",
        default=".",
        help="Root path containing .agents/planning/ (default: current directory)",
    )
    parser.add_argument(
        "--estimate-threshold",
        type=int,
        default=20,
        help="Percentage threshold for flagging estimate divergence (default: 20)",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Treat warnings as errors and exit with code 1",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit with code 1 if errors found (for CI)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for planning artifact validation."""
    parser = build_parser()
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()

    print("=== Planning Artifact Validation ===")
    print()
    print(f"Scanning path: {root}")
    if args.feature_name:
        print(f"Feature: {args.feature_name}")
    print(f"Estimate threshold: {args.estimate_threshold}%")
    print()

    docs = find_planning_documents(root, args.feature_name)

    if docs is None or not docs.all_docs:
        print("No planning documents found in .agents/planning/")
        return 0

    print(f"Found {len(docs.all_docs)} planning document(s)")
    print()

    summary = ValidationSummary()

    validate_estimates(docs, args.estimate_threshold, summary)
    print()

    validate_conditions(docs, summary)
    print()

    validate_document_structure(docs)

    print_summary(summary)

    if summary.errors and args.fail_on_error:
        return 1
    if summary.warnings and args.fail_on_warning:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
