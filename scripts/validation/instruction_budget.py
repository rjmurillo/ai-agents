#!/usr/bin/env python3
"""Measure and gate the always-on instruction budget per file language.

Issue #3419: editing a single ``.py`` file loads ~218 KB of always-on
instruction text (every ``.github/instructions/*.instructions.md`` whose
``applyTo`` matches that language regardless of directory). The IFScale
benchmark (arXiv:2507.11538) shows even the strongest models omit instructions
as the always-loaded set grows; omission, not modification, is the failure mode.
Without an instrument this corpus grows silently on every rule addition.

This validator computes the *language-baseline always-on budget*: the summed
bytes of instruction files whose ``applyTo`` includes a language-universal
pattern (``**``, ``**/*``, or ``**/*.<ext>``) for a representative extension. Directory
scoped rules (for example ``tests/**``) are situational, not always-on, so they
are excluded by design.

The per-extension ceilings are a NON-REGRESSION RATCHET seeded just above the
current measured bytes. Phase 1 (this instrument) makes the budget visible in CI
and blocks silent growth, for example adding a new all-language rule. The
follow-up rescope (#3419 AC #2) lowers these ceilings as book-derived rules move
to task-invoked skills. Lower a ceiling when the corpus shrinks; never raise one
without recording why in the same change.

Gate is on bytes (exact and reproducible). Estimated tokens are informational
and reuse the shared estimator from ``token_budget``.

Exit codes follow ADR-035:
    0 - Success (all extensions within budget, or non-CI mode)
    1 - Logic error (budget exceeded, CI mode only)
    2 - Configuration error (invalid path or missing instructions directory)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from scripts.validation.instruction_budget_constants import (
    DEFAULT_CEILINGS_BYTES,
    INSTRUCTION_GLOB,
    INSTRUCTIONS_SUBDIR,
)
from scripts.validation.instruction_budget_globs import (
    UnsupportedApplyToError,
    _glob_to_regex,
    _vscode_effective_glob,
    is_language_universal,
    parse_applyto,
)
from scripts.validation.instruction_budget_types import ExtensionResult, InstructionFile
from scripts.validation.token_budget import estimate_token_count

__all__ = [
    "DEFAULT_CEILINGS_BYTES",
    "INSTRUCTIONS_SUBDIR",
    "ExtensionResult",
    "InstructionFile",
    "UnsupportedApplyToError",
    "_glob_to_regex",
    "_vscode_effective_glob",
    "build_parser",
    "evaluate",
    "format_json",
    "format_table",
    "is_language_universal",
    "load_instruction_files",
    "main",
    "measure_extension",
    "parse_applyto",
    "parse_ceiling_override",
]


def _resolve_safe(repo_root: Path, relative: str) -> Path | None:
    """Resolve a relative path safely within repo_root (CWE-22 protection)."""
    candidate = (repo_root / relative).resolve()
    root_resolved = repo_root.resolve()
    if not candidate.is_relative_to(root_resolved):
        return None
    return candidate


def load_instruction_files(repo_root: Path) -> list[InstructionFile]:
    """Read every instruction file, measuring size and parsing ``applyTo``."""
    instructions_dir = _resolve_safe(repo_root, INSTRUCTIONS_SUBDIR)
    if instructions_dir is None or not instructions_dir.is_dir():
        return []
    files: list[InstructionFile] = []
    for path in sorted(instructions_dir.rglob(INSTRUCTION_GLOB)):
        content = path.read_text(encoding="utf-8", errors="replace")
        files.append(
            InstructionFile(
                name=path.name,
                size_bytes=len(content.encode("utf-8")),
                estimated_tokens=estimate_token_count(content),
                patterns=frozenset(parse_applyto(content)),
            )
        )
    return files


def measure_extension(
    files: list[InstructionFile],
    ext: str,
    ceiling_bytes: int,
) -> ExtensionResult:
    """Sum the always-on budget for one extension across all instruction files."""
    matched = [f for f in files if is_language_universal(set(f.patterns), ext)]
    return ExtensionResult(
        extension=ext,
        matched_files=tuple(f.name for f in matched),
        total_bytes=sum(f.size_bytes for f in matched),
        estimated_tokens=sum(f.estimated_tokens for f in matched),
        ceiling_bytes=ceiling_bytes,
    )


def evaluate(repo_root: Path, ceilings: dict[str, int]) -> list[ExtensionResult]:
    """Measure the always-on budget for every configured extension."""
    files = load_instruction_files(repo_root)
    return [
        measure_extension(files, ext, ceilings[ext])
        for ext in sorted(ceilings)
    ]


def format_table(results: list[ExtensionResult]) -> str:
    """Format results as a readable table."""
    lines: list[str] = []
    header = (
        f"{'Ext':<6} {'Files':>6} {'Bytes':>9} "
        f"{'Ceiling':>9} {'Tokens~':>9} {'Usage':>8} {'Status':>7}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for r in results:
        status = "FAIL" if r.over_budget else "PASS"
        lines.append(
            f"{r.extension:<6} {len(r.matched_files):>6} {r.total_bytes:>9} "
            f"{r.ceiling_bytes:>9} {r.estimated_tokens:>9} {r.usage_percent:>7.1f}% {status:>7}"
        )
    return "\n".join(lines)


def format_json(results: list[ExtensionResult]) -> str:
    """Format results as JSON for machine consumption."""
    data = [
        {
            "extension": r.extension,
            "matched_files": list(r.matched_files),
            "file_count": len(r.matched_files),
            "total_bytes": r.total_bytes,
            "estimated_tokens": r.estimated_tokens,
            "ceiling_bytes": r.ceiling_bytes,
            "usage_percent": r.usage_percent,
            "over_budget": r.over_budget,
        }
        for r in results
    ]
    return json.dumps(data, indent=2)


def parse_ceiling_override(value: str) -> tuple[str, int]:
    """Parse a '.ext:bytes' ceiling override string."""
    parts = value.rsplit(":", 1)
    if len(parts) != 2:
        msg = f"Invalid ceiling format '{value}'. Expected '.ext:bytes'."
        raise argparse.ArgumentTypeError(msg)
    ext = parts[0] if parts[0].startswith(".") else f".{parts[0]}"
    try:
        ceiling = int(parts[1])
    except ValueError:
        msg = f"Invalid byte count in '{value}'. Must be an integer."
        raise argparse.ArgumentTypeError(msg) from None
    if ceiling <= 0:
        msg = f"Ceiling must be positive, got {ceiling}."
        raise argparse.ArgumentTypeError(msg)
    return ext, ceiling


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Measure and gate the always-on instruction budget per language.",
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
        "--ceiling",
        action="append",
        type=parse_ceiling_override,
        default=[],
        metavar="EXT:BYTES",
        help="Override ceiling for an extension (e.g., '.py:200000'). Repeatable.",
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

    if _resolve_safe(repo_path, INSTRUCTIONS_SUBDIR) is None or not (
        repo_path / INSTRUCTIONS_SUBDIR
    ).is_dir():
        print(f"Error: instructions directory not found: {INSTRUCTIONS_SUBDIR}", file=sys.stderr)
        return 2

    ceilings = dict(DEFAULT_CEILINGS_BYTES)
    for ext, ceiling in args.ceiling:
        ceilings[ext] = ceiling

    try:
        results = evaluate(repo_path, ceilings)
    except UnsupportedApplyToError as exc:
        print(f"Error: unsupported applyTo in an instruction file: {exc}", file=sys.stderr)
        return 2
    any_over = any(r.over_budget for r in results)

    if args.output_format == "json":
        print(format_json(results))
    else:
        print("Always-On Instruction Budget (language baseline)")
        print()
        print(format_table(results))
        if any_over:
            print()
            print("FAIL: One or more languages exceed the always-on instruction ceiling.")
            print()
            print("Action Required:")
            print("  1. Move situational or book-derived rules to task-invoked skills (#3419).")
            print("  2. Scope rules with a narrower applyTo instead of '**' or '**/*.<ext>'.")
            print("  3. If a raise is truly justified, edit DEFAULT_CEILINGS_BYTES and say why.")
        else:
            print()
            print("PASS: All languages within the always-on instruction ceiling.")

    if any_over and args.ci:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
