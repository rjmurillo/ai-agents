#!/usr/bin/env python3
"""Validate workspace file token budget per issue #1334.

Workspace files (CLAUDE.md, AGENTS.md, .claude/CLAUDE.md) are injected into
every agent session context. This script enforces size limits to prevent
token waste and context truncation.

Limits:
  - Total across all workspace files: 6600 bytes
  - Per-file maximum: 3000 bytes

EXIT CODES:
  0  - Success: All workspace files within budget
  1  - Error: Budget exceeded

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Budget constants (bytes)
TOTAL_BUDGET_BYTES = 6600
PER_FILE_BUDGET_BYTES = 3000

# Workspace files injected into agent context (relative to repo root)
WORKSPACE_FILES = [
    "CLAUDE.md",
    "AGENTS.md",
    ".claude/CLAUDE.md",
]


@dataclass
class FileMetric:
    """Size measurement for a single workspace file."""

    path: str
    size_bytes: int
    exists: bool


@dataclass
class BudgetResult:
    """Accumulated budget validation results."""

    files: list[FileMetric] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


def measure_workspace_files(
    repo_root: Path,
    workspace_files: list[str] | None = None,
) -> list[FileMetric]:
    """Measure byte sizes of workspace files."""
    targets = workspace_files or WORKSPACE_FILES
    metrics: list[FileMetric] = []
    for rel_path in targets:
        full_path = repo_root / rel_path
        if full_path.is_file():
            size = full_path.stat().st_size
            metrics.append(FileMetric(path=rel_path, size_bytes=size, exists=True))
        else:
            metrics.append(FileMetric(path=rel_path, size_bytes=0, exists=False))
    return metrics


def validate_budget(
    metrics: list[FileMetric],
    total_budget: int = TOTAL_BUDGET_BYTES,
    per_file_budget: int = PER_FILE_BUDGET_BYTES,
) -> BudgetResult:
    """Check measured files against budget limits."""
    result = BudgetResult(files=metrics)

    for fm in metrics:
        if not fm.exists:
            continue
        if fm.size_bytes > per_file_budget:
            result.errors.append(
                f"{fm.path}: {fm.size_bytes} bytes exceeds "
                f"per-file limit of {per_file_budget} bytes"
            )

    total = result.total_bytes
    if total > total_budget:
        result.errors.append(
            f"Total workspace size {total} bytes exceeds budget of {total_budget} bytes"
        )

    return result


def main(argv: list[str] | None = None) -> int:
    """Entry point for workspace budget validation."""
    parser = argparse.ArgumentParser(
        description="Validate workspace file token budget per issue #1334."
    )
    parser.add_argument(
        "--path",
        default=".",
        help="Path to repository root (default: current directory)",
    )
    parser.add_argument(
        "--total-budget",
        type=int,
        default=TOTAL_BUDGET_BYTES,
        help=f"Total budget in bytes (default: {TOTAL_BUDGET_BYTES})",
    )
    parser.add_argument(
        "--per-file-budget",
        type=int,
        default=PER_FILE_BUDGET_BYTES,
        help=f"Per-file budget in bytes (default: {PER_FILE_BUDGET_BYTES})",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.path).resolve()
    metrics = measure_workspace_files(repo_root)
    result = validate_budget(metrics, args.total_budget, args.per_file_budget)

    # Print file summary
    for fm in result.files:
        if not fm.exists:
            status = "MISSING"
        elif fm.size_bytes > args.per_file_budget:
            status = "OVER"
        else:
            status = "OK"
        print(f"  {fm.path}: {fm.size_bytes:,} bytes [{status}]")

    print(f"  Total: {result.total_bytes:,} / {args.total_budget:,} bytes")

    for error in result.errors:
        print(f"ERROR: {error}")
    for warning in result.warnings:
        print(f"WARNING: {warning}")

    if result.is_valid:
        print("Workspace budget validation passed.")
        return 0

    print(f"Workspace budget validation failed. {len(result.errors)} error(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
