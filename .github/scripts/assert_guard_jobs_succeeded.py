#!/usr/bin/env python3
"""Fail the aggregate guard status unless every upstream job succeeded.

ADR-006 keeps logic out of workflow YAML, so the aggregation rule lives here.

The rule is deliberately strict. A required status check exists to answer one
question: did the guard actually run and pass? Treating "skipped" or
"cancelled" as acceptable would let a required check report success on a run
where nothing was verified, which is the false-green this guard was created to
prevent (issue #4672).
"""

from __future__ import annotations

import json
import os
import sys

_ACCEPTABLE = {"success"}


def evaluate(needs: dict[str, dict[str, str]]) -> list[str]:
    """Return one message per job that did not succeed."""
    if not needs:
        return ["no upstream jobs reported; the guard did not run"]
    problems = []
    for job, payload in sorted(needs.items()):
        result = (payload or {}).get("result", "missing")
        if result not in _ACCEPTABLE:
            problems.append(f"{job}: {result}")
    return problems


def main(argv: list[str] | None = None) -> int:
    raw = os.environ.get("NEEDS_JSON", "").strip()
    if not raw:
        print("NEEDS_JSON is empty; refusing to report success", file=sys.stderr)
        return 1
    try:
        needs = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"NEEDS_JSON is not valid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(needs, dict):
        print(f"NEEDS_JSON must be an object, got {type(needs).__name__}", file=sys.stderr)
        return 1

    problems = evaluate(needs)
    if problems:
        print("Plugin hook guard did not fully pass:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(f"All {len(needs)} plugin hook guard jobs succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
