#!/usr/bin/env python3
"""Block git push on markdownlint violations in changed .md files.

Thin adapter over :mod:`push_guard_base`. Activates on ``*.md`` files in
the push changeset and runs the co-located ``_markdownlint_verifier.py``
(a pure-Python linter using shipped ``markdown-it-py``). No external
binaries, no registry downloads, no consumer configs or plugins.

Customer value: prevents markdown lint failures from reaching consumer branches.

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (no .md files or markdownlint clean)
    2 = Block (trusted verifier unavailable, failed, or reported violations)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _bootstrap import ensure_plugin_paths

ensure_plugin_paths()

from hook_utilities import get_project_directory  # noqa: E402
from push_guard_base import run_guard  # noqa: E402

GUARD_NAME = "markdown-lint"
VERIFIER = Path(__file__).resolve().with_name("_markdownlint_verifier.py")
SAFE_CONFIG = Path(__file__).resolve().with_name("markdownlint-safe-config.yaml")
SUBPROCESS_TIMEOUT = 60


def _resolve_invocation() -> list[str] | None:
    """Return invocation args if shipped verifier and config exist."""
    if VERIFIER.is_file() and SAFE_CONFIG.is_file():
        return [sys.executable, "-I", "-S", str(VERIFIER)]
    return None


def _validate(matching: list[str], _all_changed: list[str]) -> list[str]:
    invocation = _resolve_invocation()
    if invocation is None:
        message = f"trusted verifier unavailable: {VERIFIER} or {SAFE_CONFIG} missing"
        print(f"[{GUARD_NAME}] {message}; blocking push", file=sys.stderr)
        return [message]

    print(f"[{GUARD_NAME}] using trusted verifier {VERIFIER.name}", file=sys.stderr)

    project_dir = get_project_directory()
    # Scrub PYTHON* vars so consumer sitecustomize/PYTHONPATH cannot inject.
    env = {
        k: v for k, v in __import__("os").environ.items()
        if not k.startswith("PYTHON")
    }
    try:
        proc = subprocess.run(
            [*invocation, "--markdown-lint-only", "--", *matching],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
            shell=False,
            check=False,
            cwd=project_dir,
            env=env,
        )
    except subprocess.TimeoutExpired:
        message = f"{VERIFIER.name} exceeded {SUBPROCESS_TIMEOUT}s"
        print(f"[TIMEOUT] {message}; blocking push", file=sys.stderr)
        return [message]
    except OSError as exc:
        message = f"{VERIFIER.name} failed to invoke: {exc}"
        print(f"[OSError] {message}; blocking push", file=sys.stderr)
        return [message]

    if proc.returncode == 0:
        return []

    violations = [line for line in proc.stderr.splitlines() if line.strip()]
    if not violations:
        violations = [line for line in proc.stdout.splitlines() if line.strip()]
    if not violations:
        violations = [f"{VERIFIER.name} exited {proc.returncode} without diagnostics"]
    return violations


def main() -> int:
    return run_guard(
        _validate,
        ["*.md"],
        GUARD_NAME,
        project_only=False,
        fail_closed=True,
    )


if __name__ == "__main__":
    sys.exit(main())
