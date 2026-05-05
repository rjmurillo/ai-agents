#!/usr/bin/env python3
"""Block git push on markdownlint violations in changed .md files.

Thin adapter over :mod:`push_guard_base`. Activates on ``*.md`` files in
the push changeset and runs ``markdownlint-cli2`` against them. Failures
of the binary itself (missing PATH entry, timeout, OSError) fail-open;
only real lint violations block.

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (no .md files, binary missing, timeout, OSError, clean)
    2 = Block (markdownlint reported violations)
"""

from __future__ import annotations

import shutil
import subprocess
import sys

from _bootstrap import ensure_plugin_paths

ensure_plugin_paths()

from push_guard_base import run_guard  # noqa: E402
from hook_utilities import get_project_directory  # noqa: E402

GUARD_NAME = "markdown-lint"
BINARY = "markdownlint-cli2"
SUBPROCESS_TIMEOUT = 60
VERSION_TIMEOUT = 5


def _resolve_invocation() -> list[str] | None:
    """Pick the markdownlint invocation per ADR-043 / SESSION-PROTOCOL.

    Direct binary on PATH wins (works on dev machines with global install).
    Falls back to ``npx markdownlint-cli2`` (the documented invocation for
    fresh checkouts where only Node and the project's package.json are
    available). Returns None if neither tool is on PATH; the caller
    fail-opens in that case.
    """
    if shutil.which(BINARY) is not None:
        return [BINARY]
    if shutil.which("npx") is not None:
        return ["npx", BINARY]
    return None


def _log_version(invocation: list[str]) -> None:
    try:
        proc = subprocess.run(
            [*invocation, "--version"],
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT,
            shell=False,
            check=False,
        )
        version = (proc.stdout or proc.stderr).strip().splitlines()
        first_line = version[0] if version else "(unknown)"
        runner = invocation[0]
        print(
            f"[{GUARD_NAME}] using {runner} {BINARY} {first_line}",
            file=sys.stderr,
        )
    except (subprocess.TimeoutExpired, OSError):
        print(
            f"[{GUARD_NAME}] could not determine {BINARY} version",
            file=sys.stderr,
        )


def _validate(matching: list[str], _all_changed: list[str]) -> list[str]:
    invocation = _resolve_invocation()
    if invocation is None:
        print(
            f"[{GUARD_NAME}] neither {BINARY} nor npx found on PATH; "
            f"allowing push (fail-open)",
            file=sys.stderr,
        )
        return []

    _log_version(invocation)

    project_dir = get_project_directory()
    try:
        # --no-globs: lint only the explicit file args. Without this flag
        # markdownlint-cli2 walks the repo's default **/*.md set and may
        # report violations in files outside the changeset, which is
        # exactly the noise the pre-push gate is meant to avoid.
        proc = subprocess.run(
            [*invocation, "--no-globs", *matching],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
            shell=False,
            check=False,
            cwd=project_dir,
        )
    except subprocess.TimeoutExpired:
        print(
            f"[TIMEOUT] {BINARY} exceeded {SUBPROCESS_TIMEOUT}s; "
            f"allowing push",
            file=sys.stderr,
        )
        return []
    except OSError as exc:
        print(
            f"[OSError] {BINARY} failed to invoke: {exc}; allowing push",
            file=sys.stderr,
        )
        return []

    if proc.returncode == 0:
        return []

    violations = [
        line for line in proc.stdout.splitlines() if line.strip()
    ]
    if not violations and proc.stderr.strip():
        violations = [
            line for line in proc.stderr.splitlines() if line.strip()
        ]
    return violations


def main() -> int:
    return run_guard(_validate, ["*.md"], GUARD_NAME)


if __name__ == "__main__":
    sys.exit(main())
