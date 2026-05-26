#!/usr/bin/env python3
"""CI entry point for install-parity validation (ADR-006 thin workflow).

The workflow step in ``.github/workflows/validate-generated-agents.yml``
delegates the fetch fallback, base-ref resolution, and validator
invocation to this module so the YAML stays thin (per ADR-006: "Thin
Workflows, Testable Modules"). Without this seam, the workflow step held
a ten-line bash block that mixed environment lookup, two-step fetch, and
a fallback to ``HEAD^``. The block was untestable and duplicated logic
that already lives in ``build/scripts/validate_install_parity.py``.

Behavior:

1. Read ``PR_BASE_REF`` from the environment (falls back to ``main``).
2. Run ``git fetch --no-tags --depth=200`` then ``--unshallow`` to make
   ``origin/<base>`` resolvable when the workflow checkout is shallow.
3. Resolve the base ref: ``origin/<base>`` if it now exists, otherwise
   the push-event diff range (``${{ github.event.before }}..HEAD``)
   passed via ``PUSH_BEFORE_SHA`` so multi-commit pushes cover every
   landed commit. ``HEAD^`` is the last resort and only covers the most
   recent commit.
4. Invoke the validator with the resolved base and forward its exit code.

Exit codes follow the validator's contract: 0 clean, 1 drift, 2 config.
Any error during step 1-3 returns 2 with a stderr message.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str], *, check: bool = False, timeout: int = 60) -> tuple[int, str, str]:
    """Run a subprocess. Returns (exit_code, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, "", f"{type(exc).__name__}: {exc}"
    return proc.returncode, proc.stdout, proc.stderr


def _fetch_base_ref(base_ref: str) -> None:
    """Fetch the base ref with a bounded depth, then unshallow if needed.

    Both calls tolerate failure: the first one fails when the base is
    already present; the second when the repo is not shallow. We never
    raise here, the next step (rev-parse) is the authoritative check.
    """
    _run(
        ["git", "fetch", "--no-tags", "--depth=200", "origin", base_ref],
        check=False,
        timeout=60,
    )
    _run(
        ["git", "fetch", "--no-tags", "--unshallow", "origin", base_ref],
        check=False,
        timeout=120,
    )


def _resolve_base(base_ref: str) -> str | None:
    """Return the diff base, or None if no usable ref is reachable.

    Order:
      1. ``origin/<base_ref>`` if it resolves after the fetch.
      2. ``PUSH_BEFORE_SHA..HEAD`` for push events: covers every commit
         in the push, not just the last one.
      3. ``HEAD^`` as a last resort. Single-commit fallback only.
    """
    rc, _, _ = _run(
        ["git", "rev-parse", "--verify", "--quiet", f"origin/{base_ref}"],
        timeout=10,
    )
    if rc == 0:
        return f"origin/{base_ref}"

    push_before = os.environ.get("PUSH_BEFORE_SHA", "").strip()
    if push_before and push_before != "0" * 40:
        rc, _, _ = _run(
            ["git", "rev-parse", "--verify", "--quiet", push_before],
            timeout=10,
        )
        if rc == 0:
            return push_before

    rc, _, _ = _run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD^"],
        timeout=10,
    )
    if rc == 0:
        return "HEAD^"
    return None


def main() -> int:
    base_ref = os.environ.get("PR_BASE_REF", "main").strip() or "main"
    print(f"Fetching {base_ref} for diff base...", flush=True)
    _fetch_base_ref(base_ref)

    base = _resolve_base(base_ref)
    if base is None:
        print(
            f"error: could not resolve a diff base from origin/{base_ref}, "
            "PUSH_BEFORE_SHA, or HEAD^",
            file=sys.stderr,
        )
        return 2

    print(f"Running validate_install_parity.py against {base}...", flush=True)
    validator = _REPO_ROOT / "build" / "scripts" / "validate_install_parity.py"
    if not validator.is_file():
        print(f"error: validator not found at {validator}", file=sys.stderr)
        return 2
    rc, out, err = _run(
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
