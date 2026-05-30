#!/usr/bin/env python3
"""CI entry point for install-parity validation (ADR-006 thin workflow).

The workflow step in ``.github/workflows/validate-generated-agents.yml``
delegates the fetch fallback, base-ref resolution, and validator
invocation to this module so the YAML stays thin (per ADR-006: "Thin
Workflows, Testable Modules"). Uses shared CI runner infrastructure
from ``ci_runner_base.py``.

Behavior:

1. Read ``PR_BASE_REF`` from the environment (falls back to ``main``).
2. Run ``git fetch --no-tags --depth=200`` then ``--unshallow`` to make
   ``origin/<base>`` resolvable when the workflow checkout is shallow.
3. Resolve the base ref: ``PUSH_BEFORE_SHA`` first when set (push
   events), which ensures the full push range is validated even when
   ``origin/<base>`` equals ``HEAD``. Otherwise ``origin/<base>`` if
   it resolves. ``HEAD^`` is the last resort and only covers the most
   recent commit.
4. Invoke the validator with the resolved base and forward its exit code.

Exit codes follow the validator's contract: 0 clean, 1 drift, 2 config.
Any error during step 1-3 returns 2 with a stderr message.
"""

from __future__ import annotations

import os
import sys

from ci_runner_base import (
    REPO_ROOT,
    fetch_base_ref,
    resolve_base,
    run,
    validate_branch,
)


def main() -> int:
    raw_base_ref = os.environ.get("PR_BASE_REF", "main")
    validated = validate_branch(raw_base_ref)
    if validated is None:
        print(
            f"error: PR_BASE_REF={raw_base_ref!r} failed branch-name "
            f"allowlist; refusing to fall back. Set a valid PR_BASE_REF or "
            "unset to use the default 'main'.",
            file=sys.stderr,
        )
        return 2
    base_ref = validated
    print(f"Fetching {base_ref} for diff base...", flush=True)
    fetch_base_ref(base_ref)

    base = resolve_base(base_ref)
    if base is None:
        print(
            f"error: could not resolve a diff base from origin/{base_ref}, "
            "PUSH_BEFORE_SHA, or HEAD^",
            file=sys.stderr,
        )
        return 2

    print(f"Running validate_install_parity.py against {base}...", flush=True)
    validator = REPO_ROOT / "build" / "scripts" / "validate_install_parity.py"
    if not validator.is_file():
        print(f"error: validator not found at {validator}", file=sys.stderr)
        return 2
    rc, out, err = run(
        [sys.executable, str(validator), "--base", base],
        timeout=120,
    )
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    return rc


if __name__ == "__main__":
    sys.exit(main())
