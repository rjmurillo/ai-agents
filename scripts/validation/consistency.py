#!/usr/bin/env python3
"""Validate cross-document consistency for agent-generated artifacts.

Implements the validation procedure defined in .agents/governance/consistency-protocol.md.
Checks scope alignment, coverage, naming conventions, cross-references, and task status.

Exit codes follow ADR-035:
    0 - Success (validation passed, or not in CI mode)
    1 - Logic error (validation failures detected, CI mode only)
    2 - Config error (path not found)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Naming convention patterns
# ---------------------------------------------------------------------------

NAMING_PATTERNS: dict[str, re.Pattern[str]] = {
    "epic": re.compile(r"^EPIC-\d{3}-[\w-]+\.md$"),
    "adr": re.compile(r"^ADR-\d{3}-[\w-]+\.md$"),
    "prd": re.compile(r"^prd-[\w-]+\.md$"),
    "tasks": re.compile(r"^tasks-[\w-]+\.md$"),
    "plan": re.compile(
        r"^\d{3}-[\w-]+-plan\.md$|^(implementation-plan|plan)-[\w-]+\.md$"
    ),
    "tm": re.compile(r"^TM-\d{3}-[\w-]+\.md$"),
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Result of a single validation check."""

    passed: bool = True
    issues: list[str] = field(default_factory=list)


@dataclass
class FeatureArtifacts:
    """Paths to artifacts related to a feature."""

    epic: Path | None = None
    prd: Path | None = None
    tasks: Path | None = None
    plan: Path | None = None


@dataclass
class ValidationResult:
    """Complete validation result for a feature."""

    feature: str = ""
    checkpoint: int = 1
    passed: bool = True
    artifacts: FeatureArtifacts = field(default_factory=FeatureArtifacts)
    results: dict[str, CheckResult] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation functions
# ---------------------------------------------------------------------------


def check_naming_convention(file_path: Path, expected_type: str) -> bool:
    """Validate file naming against conventions from naming-conventions.md."""
    pattern = NAMING_PATTERNS.get(expected_type)
    if pattern is None:
        return True
    return bool(pattern.match(file_path.name))


def find_feature_artifacts(feature_name: str, base_path: Path) -> FeatureArtifacts:
    """Find all artifacts related to a feature name."""
    artifacts = FeatureArtifacts()
    agents_path = base_path / ".agents"

    # Find Epic
    roadmap_path = agents_path / "roadmap"
    if roadmap_path.is_dir():
        for f in roadmap_path.glob(f"EPIC-*-*{feature_name}*.md"):
            artifacts.epic = f
            break

    # Find PRD, Tasks, Plan
    planning_path = agents_path / "planning"
    if planning_path.is_dir():
        for f in planning_path.glob(f"prd-*{feature_name}*.md"):
            artifacts.prd = f
            break
        for f in planning_path.glob(f"tasks-*{feature_name}*.md"):
            artifacts.tasks = f
            break
        for f in planning_path.glob(f"*plan*{feature_name}*.md"):
            artifacts.plan = f
            break

    return artifacts


def get_all_features(base_path: Path) -> list[str]:
    """Discover all features from existing artifacts."""
    features: list[str] = []
    planning_path = base_path / ".agents" / "planning"

    if not planning_path.is_dir():
        return features

    for pattern, prefix in [("prd-*.md", "prd-"), ("tasks-*.md", "tasks-")]:
        for f in planning_path.glob(pattern):
            name = f.stem.removeprefix(prefix)
            if name and name not in features:
                features.append(name)

    return features


def check_scope_alignment(
    epic_path: Path | None, prd_path: Path | None
) -> CheckResult:
    """Validate that PRD scope aligns with Epic outcomes."""
    result = CheckResult()

    if not epic_path or not epic_path.exists():
        result.issues.append("Epic file not found")
        return result

    if not prd_path or not prd_path.exists():
        result.passed = False
        result.issues.append("PRD file not found")
        return result

    epic_content = epic_path.read_text(encoding="utf-8")
    prd_content = prd_path.read_text(encoding="utf-8")

    # Check if PRD references the epic
    epic_name = epic_path.name
    if epic_name not in prd_content and not re.search(
        r"EPIC-\d{3}", prd_content
    ):
        result.issues.append("PRD does not reference parent Epic")

    # Extract success criteria from epic
    criteria_match = re.search(
        r"### Success Criteria(.+?)(?=###|$)", epic_content, re.DOTALL
    )
    if criteria_match:
        criteria = criteria_match.group(1)
        criteria_count = len(re.findall(r"- \[[ x]\]", criteria))
        if criteria_count > 0:
            req_match = re.search(
                r"## Requirements(.+?)(?=##|$)", prd_content, re.DOTALL
            )
            if req_match:
                requirements = req_match.group(1)
                req_count = len(
                    re.findall(r"(?m)- \[[ x]\]|^\d+\.|^-\s", requirements)
                )
                if req_count < criteria_count:
                    result.issues.append(
                        f"PRD has fewer requirements ({req_count}) "
                        f"than Epic success criteria ({criteria_count})"
                    )

    if result.issues:
        result.passed = False

    return result


def check_requirement_coverage(
    prd_path: Path | None, tasks_path: Path | None
) -> CheckResult:
    """Validate that all PRD requirements have corresponding tasks."""
    result = CheckResult()

    if not prd_path or not prd_path.exists():
        return result

    if not tasks_path or not tasks_path.exists():
        result.passed = False
        result.issues.append("Tasks file not found for PRD")
        return result

    prd_content = prd_path.read_text(encoding="utf-8")
    tasks_content = tasks_path.read_text(encoding="utf-8")

    req_count = len(
        re.findall(r"(?m)^[\s]*[-*]\s+\[[ x]\]|^[\s]*\d+\.\s+", prd_content)
    )
    task_count = len(
        re.findall(r"(?m)^[\s]*[-*]\s+\[[ x]\]|^###\s+Task", tasks_content)
    )

    if task_count < req_count:
        result.passed = False
        result.issues.append(
            f"Fewer tasks ({task_count}) than requirements ({req_count})"
        )

    return result


def check_cross_references(file_path: Path | None, base_path: Path) -> CheckResult:
    """Validate that cross-references point to existing files."""
    result = CheckResult()

    if not file_path or not file_path.exists():
        return result

    content = file_path.read_text(encoding="utf-8")
    file_dir = file_path.parent

    for match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", content):
        link_path = match.group(2)

        # Skip URLs and anchors
        if re.match(r"^https?://", link_path) or link_path.startswith("#"):
            continue

        # Remove anchor from path
        link_path = re.sub(r"#.*$", "", link_path)

        if link_path:
            if Path(link_path).is_absolute():
                full_path = Path(link_path)
            else:
                full_path = file_dir / link_path

            # Security: Prevent path traversal (CWE-22).
            resolved = full_path.resolve()
            allowed_base = base_path.resolve()
            if not resolved.is_relative_to(allowed_base):
                result.passed = False
                result.issues.append(
                    f"Path traversal detected: {link_path}"
                )
                continue

            if not resolved.exists():
                result.passed = False
                result.issues.append(f"Broken reference: {link_path}")

    return result


def check_task_completion(tasks_path: Path | None) -> CheckResult:
    """Validate task completion status for Checkpoint 2."""
    result = CheckResult()

    if not tasks_path or not tasks_path.exists():
        return result

    content = tasks_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    current_priority = "P2"
    p0_incomplete: list[str] = []

    for line in lines:
        if re.search(r"##.*P0|Priority:\s*P0|### P0", line):
            current_priority = "P0"
        elif re.search(r"##.*P1|Priority:\s*P1|### P1", line):
            current_priority = "P1"
        elif re.search(r"##.*P2|Priority:\s*P2|### P2", line):
            current_priority = "P2"

        task_match = re.match(r"^\s*[-*]\s+\[([x ])\]\s+(.+)$", line)
        if task_match:
            is_complete = task_match.group(1) == "x"
            task_name = task_match.group(2).strip()
            if not is_complete and current_priority == "P0":
                p0_incomplete.append(task_name)

    if p0_incomplete:
        result.passed = False
        result.issues.append(f"P0 tasks incomplete: {len(p0_incomplete)}")

    return result


def check_naming_conventions(artifacts: FeatureArtifacts) -> CheckResult:
    """Validate all artifact naming conventions."""
    result = CheckResult()

    checks = [
        (artifacts.epic, "epic", "Epic"),
        (artifacts.prd, "prd", "PRD"),
        (artifacts.tasks, "tasks", "Tasks"),
        (artifacts.plan, "plan", "Plan"),
    ]

    for path, type_key, label in checks:
        if path and path.exists():
            if not check_naming_convention(path, type_key):
                result.passed = False
                result.issues.append(f"{label} naming violation: {path.name}")

    return result


# ---------------------------------------------------------------------------
# Feature validation
# ---------------------------------------------------------------------------


def validate_feature(
    feature_name: str, base_path: Path, checkpoint: int
) -> ValidationResult:
    """Run all validations for a feature."""
    validation = ValidationResult(feature=feature_name, checkpoint=checkpoint)
    artifacts = find_feature_artifacts(feature_name, base_path)
    validation.artifacts = artifacts

    if checkpoint >= 1:
        scope_result = check_scope_alignment(artifacts.epic, artifacts.prd)
        validation.results["ScopeAlignment"] = scope_result
        if not scope_result.passed:
            validation.passed = False
            validation.issues.extend(scope_result.issues)

        coverage_result = check_requirement_coverage(artifacts.prd, artifacts.tasks)
        validation.results["RequirementCoverage"] = coverage_result
        if not coverage_result.passed:
            validation.passed = False
            validation.issues.extend(coverage_result.issues)

        naming_result = check_naming_conventions(artifacts)
        validation.results["NamingConventions"] = naming_result
        if not naming_result.passed:
            validation.passed = False
            validation.issues.extend(naming_result.issues)

        ref_issues: list[str] = []
        for artifact_path in [
            artifacts.epic,
            artifacts.prd,
            artifacts.tasks,
            artifacts.plan,
        ]:
            if artifact_path:
                ref_result = check_cross_references(artifact_path, base_path)
                if not ref_result.passed:
                    ref_issues.extend(ref_result.issues)
        validation.results["CrossReferences"] = CheckResult(
            passed=len(ref_issues) == 0, issues=ref_issues
        )
        if ref_issues:
            validation.passed = False
            validation.issues.extend(ref_issues)

    if checkpoint >= 2:
        task_result = check_task_completion(artifacts.tasks)
        validation.results["TaskCompletion"] = task_result
        if not task_result.passed:
            validation.passed = False
            validation.issues.extend(task_result.issues)

    return validation


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_console_output(validations: list[ValidationResult]) -> int:
    """Print console output and return failure count."""
    print("=== Consistency Validation ===")
    print()

    total_failed = 0

    for v in validations:
        status = "PASS" if v.passed else "FAIL"
        print(f"Feature: {v.feature} - {status}")

        if v.artifacts.epic:
            print(f"  Epic: {v.artifacts.epic.name}")
        if v.artifacts.prd:
            print(f"  PRD: {v.artifacts.prd.name}")
        if v.artifacts.tasks:
            print(f"  Tasks: {v.artifacts.tasks.name}")

        for check_name, check in v.results.items():
            check_status = "[PASS]" if check.passed else "[FAIL]"
            print(f"  {check_status} {check_name}")
            if not check.passed and check.issues:
                for issue in check.issues:
                    print(f"    - {issue}")

        if not v.passed:
            total_failed += 1
        print()

    print("=== Summary ===")
    passed = len(validations) - total_failed
    print(f"Passed: {passed}")
    if total_failed > 0:
        print(f"Failed: {total_failed}")

    return total_failed


def format_markdown_output(
    validations: list[ValidationResult], checkpoint: int
) -> str:
    """Format results as a markdown report."""
    lines: list[str] = [
        "# Consistency Validation Report",
        "",
        f"**Date**: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}",
        f"**Checkpoint**: {checkpoint}",
        "",
    ]

    for v in validations:
        status = "PASSED" if v.passed else "FAILED"
        lines.append(f"## Feature: {v.feature}")
        lines.append("")
        lines.append(f"**Status**: {status}")
        lines.append("")

        lines.append("### Artifacts")
        lines.append("")
        lines.append("| Artifact | Path | Found |")
        lines.append("|----------|------|-------|")

        for label, path in [
            ("Epic", v.artifacts.epic),
            ("PRD", v.artifacts.prd),
            ("Tasks", v.artifacts.tasks),
            ("Plan", v.artifacts.plan),
        ]:
            found = "Yes" if path and path.exists() else "No"
            display = path.name if path else "-"
            lines.append(f"| {label} | {display} | {found} |")

        lines.append("")
        lines.append("### Validation Results")
        lines.append("")
        lines.append("| Check | Status | Issues |")
        lines.append("|-------|--------|--------|")

        for check_name, check in v.results.items():
            check_status = "PASS" if check.passed else "FAIL"
            issues = "; ".join(check.issues) if check.issues else "-"
            lines.append(f"| {check_name} | {check_status} | {issues} |")

        lines.append("")

    return "\n".join(lines)


def format_json_output(
    validations: list[ValidationResult], checkpoint: int
) -> str:
    """Format results as JSON."""
    output = {
        "timestamp": datetime.now(UTC).isoformat(),
        "checkpoint": checkpoint,
        "validations": [
            {
                "feature": v.feature,
                "passed": v.passed,
                "artifacts": {
                    "epic": str(v.artifacts.epic) if v.artifacts.epic else None,
                    "prd": str(v.artifacts.prd) if v.artifacts.prd else None,
                    "tasks": str(v.artifacts.tasks) if v.artifacts.tasks else None,
                    "plan": str(v.artifacts.plan) if v.artifacts.plan else None,
                },
                "results": {
                    name: {"passed": r.passed, "issues": r.issues}
                    for name, r in v.results.items()
                },
                "issues": v.issues,
            }
            for v in validations
        ],
        "summary": {
            "total": len(validations),
            "passed": sum(1 for v in validations if v.passed),
            "failed": sum(1 for v in validations if not v.passed),
        },
    }
    return json.dumps(output, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with env var defaults."""
    parser = argparse.ArgumentParser(
        description="Validate cross-document consistency for agent artifacts.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--feature",
        default=os.environ.get("FEATURE"),
        help="Feature name to validate (env: FEATURE)",
    )
    group.add_argument(
        "--all",
        action="store_true",
        dest="validate_all",
        help="Validate all features",
    )
    parser.add_argument(
        "--checkpoint",
        type=int,
        choices=[1, 2],
        default=int(os.environ.get("CHECKPOINT", "1")),
        help="Checkpoint to validate: 1 (Pre-Critic) or 2 (Post-Implementation)",
    )
    parser.add_argument(
        "--format",
        choices=["console", "markdown", "json"],
        default=os.environ.get("OUTPUT_FORMAT", "console"),
        dest="output_format",
        help="Output format (env: OUTPUT_FORMAT, default: console)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        default=os.environ.get("CI", "").lower() in ("true", "1"),
        help="CI mode: exit 1 on failures (env: CI)",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("REPO_PATH", "."),
        help="Base path to scan (env: REPO_PATH, default: '.')",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    base_path = Path(args.path).resolve()

    if not base_path.is_dir():
        print(f"Error: Path not found: {args.path}", file=sys.stderr)
        return 2  # ADR-035: config error

    if args.output_format == "console":
        print("=== Consistency Validation ===")
        print(f"Path: {base_path}")
        print(f"Checkpoint: {args.checkpoint}")
        print()

    validations: list[ValidationResult] = []

    if args.validate_all:
        features = get_all_features(base_path)
        if args.output_format == "console":
            print(f"Found {len(features)} feature(s)")
            print()
        for f in features:
            validations.append(validate_feature(f, base_path, args.checkpoint))
    else:
        validations.append(
            validate_feature(args.feature, base_path, args.checkpoint)
        )

    fail_count = 0
    if args.output_format == "console":
        fail_count = format_console_output(validations)
    elif args.output_format == "markdown":
        md = format_markdown_output(validations, args.checkpoint)
        print(md)
        fail_count = sum(1 for v in validations if not v.passed)
    elif args.output_format == "json":
        json_str = format_json_output(validations, args.checkpoint)
        print(json_str)
        fail_count = sum(1 for v in validations if not v.passed)

    if args.ci and fail_count > 0:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
