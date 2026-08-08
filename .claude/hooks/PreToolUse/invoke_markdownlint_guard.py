#!/usr/bin/env python3
"""Block git push on markdownlint violations in changed .md files.

Thin adapter over :mod:`push_guard_base`. Activates on ``*.md`` files in
the push changeset and runs the plugin-shipped ``pre_pr.py`` verifier with a
safe markdownlint config. Missing verifier files, timeouts, invocation
failures, and lint violations all block.

Customer value: prevents markdown lint failures from reaching consumer branches.

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (no .md files or markdownlint clean)
    2 = Block (trusted verifier unavailable, failed, or reported violations)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from _bootstrap import ensure_plugin_paths

ensure_plugin_paths()

from hook_utilities import get_project_directory  # noqa: E402
from push_guard_base import run_guard  # noqa: E402

GUARD_NAME = "markdown-lint"
VERIFIER = Path(__file__).resolve().parents[3] / "scripts" / "validation" / "pre_pr.py"
SAFE_CONFIG = Path(__file__).resolve().with_name("markdownlint-safe-config.yaml")
SUBPROCESS_TIMEOUT = 60


def _resolve_invocation() -> list[str] | None:
    """Pick the trusted verifier shipped with the plugin.

    The verifier is invoked by absolute path so consumer-local binaries and
    `node_modules/.bin` shims are never consulted. If the verifier or its safe
    config is missing, the hook fails closed.
    """
    if VERIFIER.is_file() and SAFE_CONFIG.is_file():
        return [sys.executable, str(VERIFIER)]
    return None


def _log_verifier() -> None:
    print(
        f"[{GUARD_NAME}] using trusted verifier {VERIFIER.name}",
        file=sys.stderr,
    )


def _validate(matching: list[str], _all_changed: list[str]) -> list[str]:
    invocation = _resolve_invocation()
    if invocation is None:
        message = f"trusted verifier unavailable: {VERIFIER} or {SAFE_CONFIG} missing"
        print(
            f"[{GUARD_NAME}] {message}; blocking push",
            file=sys.stderr,
        )
        return [message]

    _log_verifier()

    project_dir = get_project_directory()
    env = os.environ.copy()
    env["MARKDOWNLINT_CONFIG_PATH"] = str(SAFE_CONFIG)
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
        print(
            f"[TIMEOUT] {message}; blocking push",
            file=sys.stderr,
        )
        return [message]
    except OSError as exc:
        message = f"{VERIFIER.name} failed to invoke: {exc}"
        print(
            f"[OSError] {message}; blocking push",
            file=sys.stderr,
        )
        return [message]

    if proc.returncode == 0:
        return []

    violations = [
        line for line in proc.stdout.splitlines() if line.strip()
    ]
    if not violations and proc.stderr.strip():
        violations = [
            line for line in proc.stderr.splitlines() if line.strip()
        ]
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
