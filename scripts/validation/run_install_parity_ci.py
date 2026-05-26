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
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Allowlist for env-supplied refs. Branch names: letters, digits, slash,
# hyphen, underscore, dot. SHA: 7-40 hex chars. Anything outside these
# shapes is refused before it reaches subprocess. This is defense in
# depth: subprocess already uses argv (no shell), but a malformed ref
# could still confuse git or trigger unexpected behavior, and CWE-78
# remediation in this repo prefers an allowlist over shlex.quote.
_BRANCH_RE = re.compile(r"^[A-Za-z0-9_./-]{1,200}$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


def _validate_branch(name: str) -> str | None:
    """Return ``name`` when it matches the branch allowlist, else None."""
    name = name.strip()
    if not name:
        return None
    if not _BRANCH_RE.match(name):
        return None
    # Disallow refs that try to escape via .. or leading -.
    if ".." in name or name.startswith("-"):
        return None
    return name


def _validate_sha(value: str) -> str | None:
    """Return ``value`` when it matches the SHA allowlist, else None."""
    value = value.strip()
    if not value:
        return None
    if not _SHA_RE.match(value):
        return None
    if value == "0" * len(value):
        return None
    return value


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
      1. ``PUSH_BEFORE_SHA`` for push events: covers every commit
         in the push, not just the last one. Checked first because
         on push events ``origin/<base_ref>`` may equal ``HEAD``,
         yielding an empty diff.
      2. ``origin/<base_ref>`` if it resolves after the fetch.
      3. ``HEAD^`` as a last resort. Single-commit fallback only.
    """
    push_before = _validate_sha(os.environ.get("PUSH_BEFORE_SHA", ""))
    if push_before is not None:
        rc, _, _ = _run(
            ["git", "rev-parse", "--verify", "--quiet", push_before],
            timeout=10,
        )
        if rc == 0:
            return push_before

    rc, _, _ = _run(
        ["git", "rev-parse", "--verify", "--quiet", f"origin/{base_ref}"],
        timeout=10,
    )
    if rc == 0:
        return f"origin/{base_ref}"

    rc, _, _ = _run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD^"],
        timeout=10,
    )
    if rc == 0:
        return "HEAD^"
    return None


def main() -> int:
    raw_base_ref = os.environ.get("PR_BASE_REF", "main")
    base_ref = _validate_branch(raw_base_ref) or "main"
    if base_ref != raw_base_ref.strip():
        print(
            f"warning: PR_BASE_REF={raw_base_ref!r} failed branch-name "
            f"allowlist; falling back to 'main'",
            file=sys.stderr,
        )
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
