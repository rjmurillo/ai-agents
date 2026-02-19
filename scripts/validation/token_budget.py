#!/usr/bin/env python3
"""Validate HANDOFF.md token budget to prevent exceeding context limits.

Checks if .agents/HANDOFF.md exceeds the 5K token budget.
Used in pre-commit hooks to block commits that would exceed the limit.

Token estimation uses heuristics based on text characteristics:
- Base: ~4 chars/token for English prose
- Non-ASCII: Increases token count (multilingual, emojis)
- Punctuation-heavy + low whitespace: Code-like text, denser tokenization
- Digit-heavy: Numbers and IDs tokenize differently
- Safety margin: 5% buffer to fail safe

Exit codes follow ADR-035:
    0 - Success (within budget or file not found)
    1 - Logic error (token budget exceeded, CI mode only)
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
import unicodedata
from pathlib import Path


def _count_punct_and_symbols(text: str) -> int:
    """Count punctuation and symbol characters (equivalent to PS \\p{P}\\p{S})."""
    count = 0
    for ch in text:
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("S"):
            count += 1
    return count


def estimate_token_count(text: str) -> int:
    """Estimate token count for text using heuristic analysis.

    Applies multiple heuristics to estimate token count more accurately than
    a simple character divisor. Accounts for non-ASCII, code-like text,
    digit-heavy content, and applies a safety margin.

    Returns estimated token count with 5% safety margin.
    """
    if not text:
        return 0

    # Normalize newlines to reduce platform variance
    normalized = text.replace("\r\n", "\n")
    char_count = len(normalized)

    # Base rule-of-thumb for English prose: ~4 chars/token
    base_tokens = math.ceil(char_count / 4.0)

    # Analyze text characteristics
    non_ascii_count = len(re.findall(r"[^\x00-\x7F]", normalized))
    punct_count = _count_punct_and_symbols(normalized)
    digit_count = len(re.findall(r"\d", normalized))
    whitespace_count = len(re.findall(r"\s", normalized))

    # Calculate density ratios (0.0 to 1.0+)
    non_ascii_ratio = non_ascii_count / char_count if char_count > 0 else 0.0
    punct_ratio = punct_count / char_count if char_count > 0 else 0.0
    digit_ratio = digit_count / char_count if char_count > 0 else 0.0
    whitespace_ratio = whitespace_count / char_count if char_count > 0 else 0.0

    # Apply multiplier adjustments based on text characteristics
    multiplier = 1.0

    # Non-ASCII (multilingual, emojis) tokenizes less efficiently
    if non_ascii_ratio > 0.01:
        adjustment = min(0.60, 2.0 * non_ascii_ratio)
        multiplier += adjustment

    # Code-like text: high punctuation, low whitespace
    if punct_ratio > 0.08 and whitespace_ratio < 0.18:
        adjustment = min(0.50, 3.0 * (punct_ratio - 0.08))
        multiplier += adjustment

    # Digit-heavy text (IDs, numbers, data)
    if digit_ratio > 0.10:
        adjustment = min(0.25, 1.5 * (digit_ratio - 0.10))
        multiplier += adjustment

    # Apply multiplier and safety margin (5% buffer to fail safe)
    safety_margin = 1.05
    estimated_tokens = math.ceil(base_tokens * multiplier * safety_margin)

    return estimated_tokens


def validate_token_budget(
    repo_path: Path,
    max_tokens: int,
    ci: bool,
) -> int:
    """Validate HANDOFF.md token budget.

    Returns ADR-035 exit code.
    """
    handoff_path = repo_path / ".agents" / "HANDOFF.md"

    if not handoff_path.exists():
        print("PASS: HANDOFF.md not found (OK for new repos)")
        return 0

    content = handoff_path.read_text(encoding="utf-8")
    estimated_tokens = estimate_token_count(content)
    file_size_kb = round(handoff_path.stat().st_size / 1024, 2)

    print("Token Budget Validation")
    print("  File: .agents/HANDOFF.md")
    print(f"  Size: {file_size_kb} KB")
    print(f"  Characters: {len(content)}")
    print(f"  Estimated tokens: {estimated_tokens} (heuristic)")
    print(f"  Budget: {max_tokens} tokens")

    if estimated_tokens > max_tokens:
        over_budget = estimated_tokens - max_tokens
        percent_over = round((over_budget / max_tokens) * 100, 1)

        print()
        print("FAIL: HANDOFF.md exceeds token budget")
        print(f"  Over budget by: {over_budget} tokens ({percent_over}%)")
        print()
        print("Action Required:")
        print("  1. Archive current content to .agents/archive/HANDOFF-YYYY-MM-DD.md")
        print("  2. Create minimal dashboard (see ADR-014)")
        print("  3. Use session logs and Serena memory for context")
        print()
        print("See: .agents/architecture/ADR-014-distributed-handoff-architecture.md")

        if ci:
            return 1
        return 0

    under_budget = max_tokens - estimated_tokens
    percent_used = round((estimated_tokens / max_tokens) * 100, 1)

    print()
    print("PASS: HANDOFF.md within token budget")
    print(f"  Remaining: {under_budget} tokens ({percent_used}% used)")

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with env var defaults."""
    parser = argparse.ArgumentParser(
        description="Validate HANDOFF.md token budget.",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("REPO_PATH", "."),
        help="Path to the repository root (env: REPO_PATH, default: '.')",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=int(os.environ.get("MAX_TOKENS", "5000")),
        help="Maximum allowed tokens (env: MAX_TOKENS, default: 5000)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        default=os.environ.get("CI", "").lower() in ("true", "1"),
        help="CI mode: exit 1 on budget exceeded (env: CI)",
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

    return validate_token_budget(repo_path, args.max_tokens, args.ci)


if __name__ == "__main__":
    raise SystemExit(main())
