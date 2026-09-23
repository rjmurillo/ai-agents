#!/usr/bin/env python3
"""Enforce blocking PR validation results.

The commit-count gate's BLOCKED status, its `commit-limit-bypass` label
check, and the advisory commit-count classifier that replaced it were all
removed (issue #5233, issue #5241). This step no longer reports or enforces
a commit count.

The removal's motivating failure was local, not here: the local pre-push
hook's bypass-label check (the now-deleted
`scripts/validation/check_pr_bypass_label.py`) shelled out to `gh api` from
inside a sandboxed Claude Code session that frequently has no GitHub token,
which forced authors into an expensive workaround (an entirely new stacked
branch and PR) to route around a check that could not confirm a fact that
was already true. This CI job runs under `GH_TOKEN: ${{ secrets.GITHUB_TOKEN
}}` (`.github/workflows/pr-validation.yml`) and never suffered that specific
access failure; its own block was removed for consistency with ADR-099's
decision to make the commit-count signal advisory everywhere, and the
classifier itself was later deleted outright (ADR-100, issue #5241).
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
