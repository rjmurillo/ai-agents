#!/usr/bin/env python3
"""Validate traceability cross-references between specification artifacts.

Implements the orphan detection algorithm defined in .agents/governance/traceability-schema.md.
Checks:
    - Rule 1: Forward Traceability (REQ -> DESIGN)
    - Rule 2: Backward Traceability (TASK -> DESIGN)
    - Rule 3: Complete Chain (DESIGN has both REQ and TASK references)
    - Rule 4: Reference Validity (all referenced IDs exist as files)
    - Rule 5: Status Consistency (completed status propagates correctly)

Exit codes follow ADR-035:
    0 - Pass (no errors; warnings allowed unless --strict)
    1 - Logic error (broken references, untraced tasks)
    2 - Config error (warnings found with --strict flag, or path issues)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SpecInfo:
    """Parsed spec file metadata from YAML front matter."""

    spec_type: str = ""
    spec_id: str = ""
    status: str = ""
    related: list[str] = field(default_factory=list)
    file_path: str = ""


@dataclass
class TraceIssue:
    """A single traceability violation."""

    rule: str
    source: str
    target: str | None
    message: str


@dataclass
class TraceResults:
    """Aggregated traceability validation results."""

    errors: list[TraceIssue] = field(default_factory=list)
    warnings: list[TraceIssue] = field(default_factory=list)
    info: list[TraceIssue] = field(default_factory=list)
    requirements_count: int = 0
    designs_count: int = 0
    tasks_count: int = 0
    valid_chains: int = 0


@dataclass
class AllSpecs:
    """All loaded specification files by category."""

    requirements: dict[str, SpecInfo] = field(default_factory=dict)
    designs: dict[str, SpecInfo] = field(default_factory=dict)
    tasks: dict[str, SpecInfo] = field(default_factory=dict)
    all: dict[str, SpecInfo] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# YAML front matter parsing
# ---------------------------------------------------------------------------


def parse_yaml_front_matter(file_path: Path) -> SpecInfo | None:
    """Extract YAML front matter from a markdown file.

    Uses simple regex parsing (not a YAML library) to match the PowerShell
    implementation behavior.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return None

    match = re.match(r"^---\r?\n(.+?)\r?\n---", content, re.DOTALL)
    if not match:
        return None

    yaml_text = match.group(1)
    spec = SpecInfo(file_path=str(file_path))

    # Parse type
    type_match = re.search(r"(?m)^type:\s*(.+)$", yaml_text)
    if type_match:
        spec.spec_type = type_match.group(1).strip()

    # Parse id
    id_match = re.search(r"(?m)^id:\s*(.+)$", yaml_text)
    if id_match:
        spec.spec_id = id_match.group(1).strip()

    # Parse status
    status_match = re.search(r"(?m)^status:\s*(.+)$", yaml_text)
    if status_match:
        spec.status = status_match.group(1).strip()

    # Parse related (array)
    related_match = re.search(
        r"(?s)related:\s*\r?\n((?:\s+-\s+.+\r?\n?)+)", yaml_text
    )
    if related_match:
        related_block = related_match.group(1)
        spec.related = [
            m.group(1) for m in re.finditer(r"-\s+([A-Z]+-[A-Z0-9]+)", related_block)
        ]

    return spec


# ---------------------------------------------------------------------------
# Spec loading
# ---------------------------------------------------------------------------


def load_all_specs(base_path: Path) -> AllSpecs:
    """Load all specification files from the specs directory."""
    specs = AllSpecs()

    # Load requirements
    req_path = base_path / "requirements"
    if req_path.is_dir():
        for f in req_path.glob("REQ-*.md"):
            spec = parse_yaml_front_matter(f)
            if spec and spec.spec_id:
                specs.requirements[spec.spec_id] = spec
                specs.all[spec.spec_id] = spec

    # Load designs
    design_path = base_path / "design"
    if design_path.is_dir():
        for f in design_path.glob("DESIGN-*.md"):
            spec = parse_yaml_front_matter(f)
            if spec and spec.spec_id:
                specs.designs[spec.spec_id] = spec
                specs.all[spec.spec_id] = spec

    # Load tasks
    task_path = base_path / "tasks"
    if task_path.is_dir():
        for f in task_path.glob("TASK-*.md"):
            spec = parse_yaml_front_matter(f)
            if spec and spec.spec_id:
                specs.tasks[spec.spec_id] = spec
                specs.all[spec.spec_id] = spec

    return specs


# ---------------------------------------------------------------------------
# Traceability validation
# ---------------------------------------------------------------------------


def validate_traceability(specs: AllSpecs) -> TraceResults:
    """Validate traceability rules and detect orphans."""
    results = TraceResults(
        requirements_count=len(specs.requirements),
        designs_count=len(specs.designs),
        tasks_count=len(specs.tasks),
    )

    # Build reference indices
    req_refs: dict[str, list[str]] = {req_id: [] for req_id in specs.requirements}
    design_refs: dict[str, list[str]] = {
        design_id: [] for design_id in specs.designs
    }

    # Build forward references from tasks to designs
    for task_id, task in specs.tasks.items():
        design_refs_for_task = [r for r in task.related if r.startswith("DESIGN-")]

        for related_id in task.related:
            if related_id.startswith("DESIGN-"):
                if related_id in specs.designs:
                    design_refs[related_id].append(task_id)
                else:
                    results.errors.append(
                        TraceIssue(
                            rule="Rule 4: Reference Validity",
                            source=task_id,
                            target=related_id,
                            message=(
                                f"TASK '{task_id}' references "
                                f"non-existent DESIGN '{related_id}'"
                            ),
                        )
                    )

        # Rule 2: Backward Traceability
        if not design_refs_for_task:
            results.errors.append(
                TraceIssue(
                    rule="Rule 2: Backward Traceability",
                    source=task_id,
                    target=None,
                    message=(
                        f"TASK '{task_id}' has no DESIGN reference (untraced task)"
                    ),
                )
            )

    # Build forward references from designs to requirements
    for design_id, design in specs.designs.items():
        for related_id in design.related:
            if related_id.startswith("REQ-"):
                if related_id in specs.requirements:
                    req_refs[related_id].append(design_id)
                else:
                    results.errors.append(
                        TraceIssue(
                            rule="Rule 4: Reference Validity",
                            source=design_id,
                            target=related_id,
                            message=(
                                f"DESIGN '{design_id}' references "
                                f"non-existent REQ '{related_id}'"
                            ),
                        )
                    )

    # Rule 1: Forward Traceability
    for req_id, refs in req_refs.items():
        if not refs:
            results.warnings.append(
                TraceIssue(
                    rule="Rule 1: Forward Traceability",
                    source=req_id,
                    target=None,
                    message=(
                        f"REQ '{req_id}' has no DESIGN referencing it "
                        f"(orphaned requirement)"
                    ),
                )
            )

    # Rule 3: Complete Chain
    for design_id, design in specs.designs.items():
        has_req_ref = any(r.startswith("REQ-") for r in design.related)
        has_task_ref = len(design_refs[design_id]) > 0

        if not has_req_ref:
            results.warnings.append(
                TraceIssue(
                    rule="Rule 3: Complete Chain",
                    source=design_id,
                    target=None,
                    message=(
                        f"DESIGN '{design_id}' has no REQ reference "
                        f"(missing backward trace)"
                    ),
                )
            )

        if not has_task_ref:
            results.warnings.append(
                TraceIssue(
                    rule="Rule 3: Complete Chain",
                    source=design_id,
                    target=None,
                    message=(
                        f"DESIGN '{design_id}' has no TASK referencing it "
                        f"(orphaned design)"
                    ),
                )
            )

        if has_req_ref and has_task_ref:
            results.valid_chains += 1

    # Rule 5: Status Consistency
    complete_statuses = {"complete", "done", "implemented"}
    for task_id, task in specs.tasks.items():
        if task.status in complete_statuses:
            for related_id in task.related:
                if related_id.startswith("DESIGN-") and related_id in specs.designs:
                    design = specs.designs[related_id]
                    if design.status not in complete_statuses:
                        results.info.append(
                            TraceIssue(
                                rule="Rule 5: Status Consistency",
                                source=task_id,
                                target=related_id,
                                message=(
                                    f"TASK '{task_id}' is complete but "
                                    f"DESIGN '{related_id}' is '{design.status}'"
                                ),
                            )
                        )

    return results


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_console(results: TraceResults) -> None:
    """Print results to console."""
    print("Traceability Validation Report")
    print("==============================")
    print()
    print("Stats:")
    print(f"  Requirements: {results.requirements_count}")
    print(f"  Designs:      {results.designs_count}")
    print(f"  Tasks:        {results.tasks_count}")
    print(f"  Valid Chains: {results.valid_chains}")
    print()

    if results.errors:
        print(f"ERRORS ({len(results.errors)}):")
        for err in results.errors:
            print(f"  [{err.rule}] {err.message}")
        print()

    if results.warnings:
        print(f"WARNINGS ({len(results.warnings)}):")
        for warn in results.warnings:
            print(f"  [{warn.rule}] {warn.message}")
        print()

    if results.info:
        print(f"INFO ({len(results.info)}):")
        for info_item in results.info:
            print(f"  [{info_item.rule}] {info_item.message}")
        print()

    if not results.errors and not results.warnings:
        print("All traceability checks passed!")


def format_markdown(results: TraceResults) -> str:
    """Format results as markdown report."""
    lines = [
        "# Traceability Validation Report",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Requirements | {results.requirements_count} |",
        f"| Designs | {results.designs_count} |",
        f"| Tasks | {results.tasks_count} |",
        f"| Valid Chains | {results.valid_chains} |",
        f"| Errors | {len(results.errors)} |",
        f"| Warnings | {len(results.warnings)} |",
        "",
    ]

    if results.errors:
        lines.append("## Errors")
        lines.append("")
        for err in results.errors:
            lines.append(f"- **{err.rule}**: {err.message}")
        lines.append("")

    if results.warnings:
        lines.append("## Warnings")
        lines.append("")
        for warn in results.warnings:
            lines.append(f"- **{warn.rule}**: {warn.message}")
        lines.append("")

    if results.info:
        lines.append("## Info")
        lines.append("")
        for info_item in results.info:
            lines.append(f"- **{info_item.rule}**: {info_item.message}")
        lines.append("")

    return "\n".join(lines)


def format_json(results: TraceResults) -> str:
    """Format results as JSON."""
    output = {
        "errors": [
            {"rule": e.rule, "source": e.source, "target": e.target, "message": e.message}
            for e in results.errors
        ],
        "warnings": [
            {"rule": w.rule, "source": w.source, "target": w.target, "message": w.message}
            for w in results.warnings
        ],
        "info": [
            {"rule": i.rule, "source": i.source, "target": i.target, "message": i.message}
            for i in results.info
        ],
        "stats": {
            "requirements": results.requirements_count,
            "designs": results.designs_count,
            "tasks": results.tasks_count,
            "validChains": results.valid_chains,
        },
    }
    return json.dumps(output, indent=2)


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


def validate_specs_path(specs_path_str: str) -> Path:
    """Resolve and validate the specs path with traversal protection.

    Raises SystemExit on path traversal attempts.
    """
    resolved = Path(specs_path_str).resolve()
    if not resolved.is_dir():
        print(f"Specs path not found: {specs_path_str}", file=sys.stderr)
        raise SystemExit(1)

    is_absolute = Path(specs_path_str).is_absolute()

    if not is_absolute:
        # Relative path: enforce traversal protection
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            repo_root = result.stdout.strip() if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            repo_root = None

        if repo_root:
            allowed_base = Path(repo_root).resolve()
            if not str(resolved).startswith(str(allowed_base)):
                print(
                    f"Path traversal attempt detected: '{specs_path_str}' "
                    f"resolves to '{resolved}' which is outside the "
                    f"repository root '{allowed_base}'.",
                    file=sys.stderr,
                )
                raise SystemExit(1)
        else:
            if ".." in specs_path_str:
                current_dir = Path.cwd().resolve()
                if not str(resolved).startswith(str(current_dir)):
                    print(
                        f"Path traversal attempt detected: '{specs_path_str}' "
                        f"resolves outside the current directory.",
                        file=sys.stderr,
                    )
                    raise SystemExit(1)

    return resolved


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with env var defaults."""
    parser = argparse.ArgumentParser(
        description="Validate traceability cross-references between spec artifacts.",
    )
    parser.add_argument(
        "--specs-path",
        default=os.environ.get("SPECS_PATH", ".agents/specs"),
        help="Path to the specs directory (env: SPECS_PATH, default: .agents/specs)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=os.environ.get("STRICT", "").lower() in ("true", "1"),
        help="Fail on warnings (orphaned specs) (env: STRICT)",
    )
    parser.add_argument(
        "--format",
        choices=["console", "markdown", "json"],
        default=os.environ.get("OUTPUT_FORMAT", "console"),
        dest="output_format",
        help="Output format (env: OUTPUT_FORMAT, default: console)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    resolved_path = validate_specs_path(args.specs_path)

    specs = load_all_specs(resolved_path)
    results = validate_traceability(specs)

    if args.output_format == "console":
        format_console(results)
    elif args.output_format == "markdown":
        print(format_markdown(results))
    elif args.output_format == "json":
        print(format_json(results))

    if results.errors:
        return 1
    if results.warnings and args.strict:
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
