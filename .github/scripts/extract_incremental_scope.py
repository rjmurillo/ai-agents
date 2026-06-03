#!/usr/bin/env python3
"""Extract incremental PR scope markers from a title.

The ai-spec-validation workflow delegates marker parsing here so YAML stays an
orchestrator. Recognized markers are explicit slices only, such as
"Phase 2 of #1799" or "PR 1 of 3". Plain phrases like "phase 2 rollout" are
not incremental scope declarations.
"""

from __future__ import annotations

import argparse
import re

_SCOPE_PATTERN = re.compile(
    r"(?i)\b("
    r"phase\s+\d+\s+of\s+#?\d+"
    r"|pr\s+\d+\s+of\s+\d+"
    r")\b"
)


def extract_incremental_scope(title: str) -> str:
    """Return the first explicit incremental scope marker, or an empty string."""
    match = _SCOPE_PATTERN.search(title)
    return " ".join(match.group(1).split()) if match else ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title", help="Pull request title to inspect")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(extract_incremental_scope(args.title))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
