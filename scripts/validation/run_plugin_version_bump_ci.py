#!/usr/bin/env python3
"""CI entry point for plugin version-bump validation (ADR-006 thin workflow).

The workflow step in ``.github/workflows/validate-plugin-version-bump.yml``
delegates fetch fallback, base-ref resolution, and validator invocation to this
module so the YAML stays thin (ADR-006: "Thin Workflows, Testable Modules").
Uses shared CI runner infrastructure from ``ci_runner_base.py``.

Behavior:

1. Read ``PR_BASE_REF`` from the environment (falls back to ``main``).
2. ``git fetch --no-tags --depth=200`` then ``--unshallow`` so ``origin/<base>``
   resolves under a shallow checkout.
3. Resolve the base via ``ci_runner_base.resolve_base``: prefer
   ``origin/<base>`` for PR and feature-branch pushes, fall back to
   ``PUSH_BEFORE_SHA`` for direct pushes to the base branch, then ``HEAD^``.
4. Invoke the validator with the resolved base and forward its exit code.

Exit codes follow the validator: 0 clean, 1 a manifest carries a ``version``
field, 2 config. Any error in steps 1-3 returns 2 with a stderr message.

Steps 2 and 3 stay because a shallow checkout still has to resolve the head ref
the validator reads the manifests from. The resolved base is passed through and
no longer changes the verdict (ADR-092).
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
            f"error: PR_BASE_REF={raw_base_ref!r} failed branch-name allowlist; "
            "refusing to fall back. Set a valid PR_BASE_REF or unset for 'main'.",
            file=sys.stderr,
        )
        return 2
    base_ref = validated
    print(f"Fetching {base_ref} for diff base...", flush=True)
    # `fetch_base_ref` is imported through a sys.path insert, so mypy
    # sees Any. int() states the contract at the boundary instead of
    # suppressing the warning.
    fetch_rc = int(fetch_base_ref(base_ref))
    if fetch_rc != 0:
        return fetch_rc

    base = resolve_base(base_ref)
    if base is None:
        print(
            f"error: could not resolve a diff base from origin/{base_ref}, "
            "PUSH_BEFORE_SHA, or HEAD^",
            file=sys.stderr,
        )
        return 2

    validator = REPO_ROOT / "build" / "scripts" / "validate_plugin_version_bump.py"
    if not validator.is_file():
        print(f"error: validator not found at {validator}", file=sys.stderr)
        return 2

    print(f"Running validate_plugin_version_bump.py against {base}...", flush=True)
    rc, out, err = run(
        [sys.executable, str(validator), "--base", base], timeout=120
    )
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    return rc


if __name__ == "__main__":
    sys.exit(main())
