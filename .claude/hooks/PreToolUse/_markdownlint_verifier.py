#!/usr/bin/env python3
"""Trusted markdown push verifier stub (fail-closed).

No immutable complete markdown linting engine is shipped with the plugin.
This stub blocks all pushes that modify .md files, preventing unchecked
markdown from reaching consumer branches.

A future release may ship a vendored, hash-verified linting engine.
Until then, the security model requires fail-closed behavior.

Interface:
    python _markdownlint_verifier.py --markdown-lint-only -- <file> [<file>...]

Exit codes:
    1 = Always: no complete engine available (blocks push).
    2 = Infrastructure/argument error.
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
        "no immutable complete markdown linting engine shipped; "
        "blocking push to prevent unchecked content",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
