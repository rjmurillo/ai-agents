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
  2  - Config/environment error (e.g. invalid path)

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

# Workspace files injected into agent context (relative to repo root).
# Claude-side files: CLAUDE.md, AGENTS.md, .claude/CLAUDE.md.
# Copilot-side file: .github/copilot-instructions.md (injected into every
# Copilot session; added to this list by issue #3991).
WORKSPACE_FILES = [
    "CLAUDE.md",
    "AGENTS.md",
    ".claude/CLAUDE.md",
    ".github/copilot-instructions.md",
]

# Per-file ceiling overrides: non-regression ratchets for files that cannot
# yet meet PER_FILE_BUDGET_BYTES. Lower when content is trimmed; never raise
# without recording the reason in the same change.
# Files listed here are measured individually; they are excluded from the
# TOTAL_BUDGET_BYTES shared pool (which applies to the Claude-side trio only).
FILE_CEILING_BYTES: dict[str, int] = {
    # Copilot always-on entry point. Ratchet seeded at 6351 bytes (measured
    # 2025-07-30 on origin/main). Target: reduce to 3000 after moving the
    # Gotchas section to .agents/governance/ (issue #3991, #3952).
    ".github/copilot-instructions.md": 6351,
}


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
    targets = WORKSPACE_FILES if workspace_files is None else workspace_files
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
    file_ceilings: dict[str, int] | None = None,
) -> BudgetResult:
    """Check measured files against budget limits.

    Files present in ``file_ceilings`` use their individual ceiling instead of
    ``per_file_budget`` and are excluded from the shared ``total_budget`` pool.
    """
    ceilings = FILE_CEILING_BYTES if file_ceilings is None else file_ceilings
    result = BudgetResult(files=metrics)

    standard_total = 0
    for fm in metrics:
        if not fm.exists:
            continue
        ceiling = ceilings.get(fm.path, per_file_budget)
        if fm.size_bytes > ceiling:
            result.errors.append(
                f"{fm.path}: {fm.size_bytes} bytes exceeds per-file limit of {ceiling} bytes"
            )
        if fm.path not in ceilings:
            standard_total += fm.size_bytes

    if standard_total > total_budget:
        result.errors.append(
            f"Total workspace size {standard_total} bytes exceeds budget of {total_budget} bytes"
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
    if not repo_root.exists() or not repo_root.is_dir():
        print(f"ERROR: Invalid repository path: {repo_root}", file=sys.stderr)
        return 2
    metrics = measure_workspace_files(repo_root)
    result = validate_budget(metrics, args.total_budget, args.per_file_budget)

    # Print file summary using the same effective ceilings as validate_budget()
    pool_total = 0
    for fm in result.files:
        if not fm.exists:
            status = "MISSING"
            ceiling_label = ""
        else:
            effective_ceiling = FILE_CEILING_BYTES.get(fm.path, args.per_file_budget)
            in_pool = fm.path not in FILE_CEILING_BYTES
            if in_pool:
                pool_total += fm.size_bytes
            if fm.size_bytes > effective_ceiling:
                status = "OVER"
            else:
                status = "OK"
            ceiling_label = f" (limit {effective_ceiling:,})"
        print(f"  {fm.path}: {fm.size_bytes:,} bytes{ceiling_label} [{status}]")

    print(f"  Pool total: {pool_total:,} / {args.total_budget:,} bytes")

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
