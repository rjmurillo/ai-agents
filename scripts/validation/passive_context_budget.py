#!/usr/bin/env python3
"""Validate passive context file token budgets.

Measures and enforces token budgets for files that are always loaded into
agent context (AGENTS.md, CLAUDE.md, memory-index). Implements the Vercel
research recommendation of <8KB compressed passive context per file.

Each file has a configurable token budget. The validator estimates token
counts using heuristics and reports usage as a table.

Exit codes follow ADR-035:
    0 - Success (all files within budget)
    1 - Logic error (budget exceeded, CI mode only)
    2 - Configuration error (invalid path)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.validation.token_budget import estimate_token_count

DEFAULT_BUDGETS: dict[str, int] = {
    "AGENTS.md": 2000,
    "CLAUDE.md": 2000,
    ".claude/CLAUDE.md": 4000,
}


@dataclass(frozen=True)
class FileResult:
    """Token budget measurement for a single file."""

    path: str
    exists: bool
    size_bytes: int
    estimated_tokens: int
    budget: int

    @property
    def usage_percent(self) -> float:
        if self.budget <= 0:
            return 0.0
        return round((self.estimated_tokens / self.budget) * 100, 1)

    @property
    def over_budget(self) -> bool:
        return self.estimated_tokens > self.budget


def _resolve_safe(repo_root: Path, relative: str) -> Path | None:
    """Resolve a relative path safely within repo_root (CWE-22 protection)."""
    candidate = (repo_root / relative).resolve()
    root_resolved = repo_root.resolve()
    if not str(candidate).startswith(str(root_resolved) + os.sep) and candidate != root_resolved:
        return None
    return candidate


def measure_file(repo_root: Path, relative_path: str, budget: int) -> FileResult:
    """Measure a single passive context file against its budget."""
    safe_path = _resolve_safe(repo_root, relative_path)
    if safe_path is None:
        return FileResult(
            path=relative_path,
            exists=False,
            size_bytes=0,
            estimated_tokens=0,
            budget=budget,
        )

    if not safe_path.is_file():
        return FileResult(
            path=relative_path,
            exists=False,
            size_bytes=0,
            estimated_tokens=0,
            budget=budget,
        )

    content = safe_path.read_text(encoding="utf-8")
    return FileResult(
        path=relative_path,
        exists=True,
        size_bytes=safe_path.stat().st_size,
        estimated_tokens=estimate_token_count(content),
        budget=budget,
    )


def validate_passive_context(
    repo_root: Path,
    budgets: dict[str, int],
) -> list[FileResult]:
    """Validate all configured passive context files. Returns results list."""
    return [
        measure_file(repo_root, rel_path, budget)
        for rel_path, budget in sorted(budgets.items())
    ]


def format_table(results: list[FileResult]) -> str:
    """Format results as a readable table."""
    lines: list[str] = []
    lines.append(f"{'File':<30} {'Size':>8} {'Tokens':>8} {'Budget':>8} {'Usage':>8} {'Status':>8}")
    lines.append("-" * 82)

    for r in results:
        if not r.exists:
            lines.append(f"{r.path:<30} {'--':>8} {'--':>8} {r.budget:>8} {'--':>8} {'SKIP':>8}")
            continue

        size_str = f"{r.size_bytes / 1024:.2f} KB"
        status = "FAIL" if r.over_budget else "PASS"
        lines.append(
            f"{r.path:<30} {size_str:>8} {r.estimated_tokens:>8} "
            f"{r.budget:>8} {r.usage_percent:>7.1f}% {status:>8}"
        )

    return "\n".join(lines)


def format_json(results: list[FileResult]) -> str:
    """Format results as JSON for machine consumption."""
    data = [
        {
            "path": r.path,
            "exists": r.exists,
            "size_bytes": r.size_bytes,
            "estimated_tokens": r.estimated_tokens,
            "budget": r.budget,
            "usage_percent": r.usage_percent,
            "over_budget": r.over_budget,
        }
        for r in results
    ]
    return json.dumps(data, indent=2)


def parse_budget_override(value: str) -> tuple[str, int]:
    """Parse a 'path:tokens' budget override string."""
    parts = value.rsplit(":", 1)
    if len(parts) != 2:
        msg = f"Invalid budget format '{value}'. Expected 'path:tokens'."
        raise argparse.ArgumentTypeError(msg)
    try:
        tokens = int(parts[1])
    except ValueError:
        msg = f"Invalid token count in '{value}'. Must be an integer."
        raise argparse.ArgumentTypeError(msg) from None
    if tokens <= 0:
        msg = f"Token budget must be positive, got {tokens}."
        raise argparse.ArgumentTypeError(msg)
    return parts[0], tokens


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Validate passive context file token budgets.",
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
        help="CI mode: exit 1 on any budget exceeded (env: CI)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        dest="output_format",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--budget",
        action="append",
        type=parse_budget_override,
        default=[],
        metavar="PATH:TOKENS",
        help="Override budget for a file (e.g., 'AGENTS.md:3000'). Repeatable.",
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

    budgets = dict(DEFAULT_BUDGETS)
    for file_path, tokens in args.budget:
        budgets[file_path] = tokens

    results = validate_passive_context(repo_path, budgets)

    any_over = any(r.over_budget for r in results if r.exists)

    if args.output_format == "json":
        print(format_json(results))
    else:
        print("Passive Context Token Budget Validation")
        print()
        print(format_table(results))

        if any_over:
            print()
            print("FAIL: One or more passive context files exceed their token budget.")
            print()
            print("Action Required:")
            print("  1. Compress content using pipe-delimited format (see context-optimizer skill)")
            print("  2. Move detailed content to skills or @-imported references")
            print("  3. Use --budget PATH:TOKENS to adjust if the default is too restrictive")
        else:
            print()
            print("PASS: All passive context files within budget.")

    if any_over and args.ci:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
