#!/usr/bin/env python3
"""Validate a cached AI-review verdict before it is written or served.

The agent-review composite action caches review verdicts keyed by commit SHA.
A cache entry replays on every rerun until the SHA changes, so a truncated or
malformed verdict cached once is served forever for that commit (Issue #2195).

This script wraps the canonical ``is_valid_cached_verdict`` check so the action
can keep verdict-shape logic out of YAML (ADR-006). The valid token set lives
in one place: ``scripts/ai_review_common/verdict.py``.

Read the verdict from a file (the cache file path) or pass it literally:

    python3 scripts/validate_cached_verdict.py --file ai-review-cache/qa/verdict.txt
    python3 scripts/validate_cached_verdict.py --verdict PASS

EXIT CODES (see ADR-035):
  0  - Valid: verdict is a well-formed, cacheable token
  1  - Invalid: empty, malformed, missing file, or non-cacheable token
  2  - Usage error: bad arguments

See: Issue #2195, ADR-006 (no logic in YAML), ADR-035 (exit codes).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow invocation as a standalone script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ai_review_common.verdict import is_valid_cached_verdict  # noqa: E402

EXIT_VALID = 0
EXIT_INVALID = 1
EXIT_USAGE = 2


def read_verdict(file_path: str | None, literal: str | None) -> str | None:
    """Return the verdict text from a file or literal, or None if unreadable.

    A missing or unreadable cache file is treated as no verdict (None), which
    the caller validates as invalid. We do not raise: a corrupt cache entry is
    an expected condition the action must recover from, not a crash.
    """
    if literal is not None:
        return literal
    path = Path(file_path) if file_path else None
    if path is None or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a cached AI-review verdict is well-formed.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--file",
        help="Path to the cached verdict file to validate.",
    )
    group.add_argument(
        "--verdict",
        help="Literal verdict token to validate.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        # argparse exits 2 on bad args; preserve that as the usage code.
        return EXIT_USAGE if exc.code else EXIT_VALID

    verdict = read_verdict(args.file, args.verdict)
    if is_valid_cached_verdict(verdict):
        shown = verdict.strip() if verdict else ""
        print(f"Cached verdict is valid: {shown}")
        return EXIT_VALID

    shown = repr(verdict) if verdict is not None else "<missing>"
    print(f"Cached verdict is invalid or malformed: {shown}", file=sys.stderr)
    return EXIT_INVALID


if __name__ == "__main__":
    raise SystemExit(main())
