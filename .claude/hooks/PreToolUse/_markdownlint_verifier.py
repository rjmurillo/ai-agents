#!/usr/bin/env python3
"""Trusted markdown push verifier -- fail-closed stub.

No integrity-pinned complete markdown linting engine is shipped with the
plugin.  An ad-hoc regex reimplementation cannot faithfully cover all
default-enabled markdownlint rules (blockquotes, Setext headings, nested
fences, etc. create parser-level edge cases).

This stub blocks all pushes that modify .md files until a vendored,
hash-verified, complete engine is available as an immutable plugin asset.

Interface:
    python _markdownlint_verifier.py --markdown-lint-only -- <file> [<file>...]

Exit codes:
    0 = No files to validate (empty list).
    1 = Files present but no complete engine available (blocks push).
    2 = Infrastructure / argument error.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if "--markdown-lint-only" not in args:
        print(
            "usage: _markdownlint_verifier.py --markdown-lint-only -- <files>",
            file=sys.stderr,
        )
        return 2
    try:
        sep_idx = args.index("--")
    except ValueError:
        print("missing -- separator", file=sys.stderr)
        return 2

    files = args[sep_idx + 1:]
    if not files:
        return 0

    print(
        "no integrity-pinned complete markdown linting engine shipped; "
        "blocking push to prevent unchecked content",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
