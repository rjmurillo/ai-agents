#!/usr/bin/env python3
"""Validate passive context files stay within token budgets.

Enforces the Vercel research recommendation (<8KB compressed) for
files loaded into agent context every turn. Measures estimated tokens
and file sizes against configurable per-file budgets.

Reference: .agents/analysis/vercel-passive-context-vs-skills-research.md

Exit codes follow ADR-035:
    0 - Success (all files within budget)
    1 - Logic error (budget exceeded, CI mode only)
    2 - Config error (invalid path or configuration)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.validation.token_budget import estimate_token_count

# Default passive context files and their token budgets.
# Budgets derived from Vercel research: 8KB compressed ~= 2000 tokens.
# AGENTS.md is the primary agent instruction file, kept lean.
# memory-index.md is the memory catalog, allowed more headroom.
_DEFAULT_TARGETS: list[dict[str, str | int]] = [
    {"path": "AGENTS.md", "max_tokens": 2000, "label": "Agent instructions"},
    {
        "path": ".serena/memories/memory-index.md",
        "max_tokens": 4000,
        "label": "Memory index",
    },
]


@dataclass(frozen=True)
class FileResult:
    """Measurement result for a single passive context file."""

    path: str
    label: str
    exists: bool
    size_bytes: int
    char_count: int
    estimated_tokens: int
    max_tokens: int

    @property
    def within_budget(self) -> bool:
        if not self.exists:
            return True
        return self.estimated_tokens <= self.max_tokens

    @property
    def usage_percent(self) -> float:
        if self.max_tokens == 0:
            return 0.0
        return round((self.estimated_tokens / self.max_tokens) * 100, 1)

    @property
    def size_kb(self) -> float:
        return round(self.size_bytes / 1024, 2)


def measure_file(repo_path: Path, target: dict[str, str | int]) -> FileResult:
    """Measure a single passive context file against its budget."""
    rel_path = str(target["path"])
    max_tokens = int(target["max_tokens"])
    label = str(target.get("label", rel_path))
    file_path = repo_path / rel_path

    if not file_path.exists():
        return FileResult(
            path=rel_path,
            label=label,
            exists=False,
            size_bytes=0,
            char_count=0,
            estimated_tokens=0,
            max_tokens=max_tokens,
        )

    content = file_path.read_text(encoding="utf-8")
    return FileResult(
        path=rel_path,
        label=label,
        exists=True,
        size_bytes=file_path.stat().st_size,
        char_count=len(content),
        estimated_tokens=estimate_token_count(content),
        max_tokens=max_tokens,
    )


def validate_passive_context(
    repo_path: Path,
    targets: list[dict[str, str | int]],
    ci: bool,
) -> tuple[list[FileResult], int]:
    """Validate all passive context files against their budgets.

    Returns a tuple of (results, exit_code).
    """
    results = [measure_file(repo_path, t) for t in targets]
    failures = [r for r in results if not r.within_budget]

    if failures and ci:
        return results, 1
    return results, 0


def print_report(results: list[FileResult]) -> None:
    """Print a human-readable budget report."""
    print("Passive Context Budget Report")
    print("=" * 50)

    for r in results:
        if not r.exists:
            print(f"\n  {r.label} ({r.path})")
            print("    Status: SKIP (file not found)")
            continue

        status = "PASS" if r.within_budget else "FAIL"
        print(f"\n  {r.label} ({r.path})")
        print(f"    Size: {r.size_kb} KB")
        print(f"    Characters: {r.char_count}")
        print(f"    Estimated tokens: {r.estimated_tokens}")
        print(f"    Budget: {r.max_tokens} tokens")
        print(f"    Usage: {r.usage_percent}%")
        print(f"    Status: {status}")

        if not r.within_budget:
            over = r.estimated_tokens - r.max_tokens
            print(f"    Over budget by: {over} tokens")
            print("    Action: Compress using pipe-delimited format")

    failures = [r for r in results if not r.within_budget]
    print()
    if failures:
        names = ", ".join(r.path for r in failures)
        print(f"FAIL: {len(failures)} file(s) over budget: {names}")
    else:
        print("PASS: All passive context files within budget")


def print_json(results: list[FileResult]) -> None:
    """Print results as JSON."""
    data = {
        "files": [
            {
                "path": r.path,
                "label": r.label,
                "exists": r.exists,
                "size_bytes": r.size_bytes,
                "size_kb": r.size_kb,
                "char_count": r.char_count,
                "estimated_tokens": r.estimated_tokens,
                "max_tokens": r.max_tokens,
                "usage_percent": r.usage_percent,
                "within_budget": r.within_budget,
            }
            for r in results
        ],
        "all_pass": all(r.within_budget for r in results),
    }
    print(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with env var defaults."""
    parser = argparse.ArgumentParser(
        description="Validate passive context files against token budgets.",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("REPO_PATH", "."),
        help="Path to the repository root (env: REPO_PATH, default: '.')",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        default=os.environ.get("CI", "").lower() in ("true", "1"),
        help="CI mode: exit 1 on budget exceeded (env: CI)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_path = Path(args.path).resolve()
    if not repo_path.is_dir():
        print(f"Error: path is not a directory: {args.path}", file=sys.stderr)
        return 2

    results, exit_code = validate_passive_context(
        repo_path, _DEFAULT_TARGETS, args.ci
    )

    if args.json:
        print_json(results)
    else:
        print_report(results)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
