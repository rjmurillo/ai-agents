#!/usr/bin/env python3
"""Enforce blocking PR validation results.

The commit-count gate's BLOCKED status and its `commit-limit-bypass` label
check were removed (issue #5230): that gate required local verification of a
GitHub label that a sandboxed harness cannot always perform, which forced
authors into an expensive workaround (an entirely new stacked branch and PR)
to route around a check that could not confirm a fact that was already true.
The commit count is still reported (see `scripts/validation/pr_commit_count.py`)
but is advisory only and never fails this step.
"""

from __future__ import annotations

import os
import sys

LOGIC_ERROR = 1


def main(argv: list[str] | None = None) -> int:
    if argv:
        print("::error::unexpected command line arguments", file=sys.stderr)
        return 2
    overall_status = os.environ.get("OVERALL_STATUS", "")
    if overall_status in {"FAIL", "ERROR"}:
        print(f"::error::PR validation failed: {overall_status}", file=sys.stderr)
        return LOGIC_ERROR
    print("✓ PR validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
