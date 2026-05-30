#!/usr/bin/env python3
"""CI entry point for plugin version-bump validation (ADR-006 thin workflow).

The workflow step in ``.github/workflows/validate-plugin-version-bump.yml``
delegates fetch fallback, base-ref resolution, and validator invocation to this
module so the YAML stays thin (ADR-006: "Thin Workflows, Testable Modules").
Mirrors ``scripts/validation/run_install_parity_ci.py``; both validators need a
diff base, and the resolution logic is identical.

Behavior:

1. Read ``PR_BASE_REF`` from the environment (falls back to ``main``).
2. ``git fetch --no-tags --depth=200`` then ``--unshallow`` so ``origin/<base>``
   resolves under a shallow checkout.
3. Resolve the base: ``PUSH_BEFORE_SHA`` first (push events, full range), then
   ``origin/<base>``, then ``HEAD^`` as last resort.
4. Invoke the validator with the resolved base and forward its exit code.

Exit codes follow the validator: 0 clean, 1 not-bumped, 2 config. Any error in
steps 1-3 returns 2 with a stderr message.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Allowlist for env-supplied refs (defense in depth; subprocess uses argv, no
# shell). Branch: letters, digits, slash, hyphen, underscore, dot. SHA: 7-40 hex.
_BRANCH_RE = re.compile(r"^[A-Za-z0-9_./-]{1,200}$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


def _validate_branch(name: str) -> str | None:
    name = name.strip()
    if not name or not _BRANCH_RE.match(name):
        return None
    if ".." in name or name.startswith("-"):
        return None
    return name


def _validate_sha(value: str) -> str | None:
    value = value.strip()
    if not value or not _SHA_RE.match(value):
        return None
    if value == "0" * len(value):
        return None
    return value


def _run(cmd: list[str], *, timeout: int = 60) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, "", f"{type(exc).__name__}: {exc}"
    return proc.returncode, proc.stdout, proc.stderr


def _fetch_base_ref(base_ref: str) -> None:
    """Fetch the base ref with bounded depth, then unshallow. Both tolerate
    failure; the authoritative check is the later rev-parse."""
    _run(
        ["git", "fetch", "--no-tags", "--depth=200", "origin", base_ref],
        timeout=60,
    )
    _run(
        ["git", "fetch", "--no-tags", "--unshallow", "origin", base_ref],
        timeout=120,
    )


def _resolve_base(base_ref: str) -> str | None:
    """Return the diff base, or None when no usable ref resolves.

    Order: PUSH_BEFORE_SHA (push events, full range) -> origin/<base_ref> ->
    HEAD^ (single-commit last resort).
    """
    push_before = _validate_sha(os.environ.get("PUSH_BEFORE_SHA", ""))
    if push_before is not None:
        rc, _, _ = _run(
            ["git", "rev-parse", "--verify", "--quiet", push_before], timeout=10
        )
        if rc == 0:
            return push_before

    rc, _, _ = _run(
        ["git", "rev-parse", "--verify", "--quiet", f"origin/{base_ref}"], timeout=10
    )
    if rc == 0:
        return f"origin/{base_ref}"

    rc, _, _ = _run(["git", "rev-parse", "--verify", "--quiet", "HEAD^"], timeout=10)
    if rc == 0:
        return "HEAD^"
    return None


def main() -> int:
    raw_base_ref = os.environ.get("PR_BASE_REF", "main")
    validated = _validate_branch(raw_base_ref)
    if validated is None:
        print(
            f"error: PR_BASE_REF={raw_base_ref!r} failed branch-name allowlist; "
            "refusing to fall back. Set a valid PR_BASE_REF or unset for 'main'.",
            file=sys.stderr,
        )
        return 2
    base_ref = validated
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

    validator = _REPO_ROOT / "build" / "scripts" / "validate_plugin_version_bump.py"
    if not validator.is_file():
        print(f"error: validator not found at {validator}", file=sys.stderr)
        return 2

    print(f"Running validate_plugin_version_bump.py against {base}...", flush=True)
    rc, out, err = _run(
        [sys.executable, str(validator), "--base", base], timeout=120
    )
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    return rc


if __name__ == "__main__":
    sys.exit(main())
