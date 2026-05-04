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

import os
import shutil
import subprocess
import sys
from pathlib import Path

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _resolved_root = Path(_plugin_root).resolve()
    _hooks_dir = str(_resolved_root / "hooks" / "PreToolUse")
    _lib_dir = str(_resolved_root / "lib")
else:
    _cur = Path(__file__).resolve().parent
    _hooks_dir = None
    _lib_dir = None
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _hooks_dir = str(_cur / "hooks" / "PreToolUse")
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _hooks_dir is None or not os.path.isdir(_hooks_dir):
    print(
        f"Plugin hooks directory not found: {_hooks_dir} "
        f"(CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
    sys.exit(2)
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print(
        f"Plugin lib directory not found: {_lib_dir} "
        f"(CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
    sys.exit(2)
if _hooks_dir not in sys.path:
    sys.path.insert(0, _hooks_dir)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from push_guard_base import run_guard  # noqa: E402
from hook_utilities import get_project_directory  # noqa: E402

GUARD_NAME = "markdown-lint"
BINARY = "markdownlint-cli2"
SUBPROCESS_TIMEOUT = 60
VERSION_TIMEOUT = 5


def _log_version() -> None:
    try:
        proc = subprocess.run(
            [BINARY, "--version"],
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT,
            shell=False,
            check=False,
        )
        version = (proc.stdout or proc.stderr).strip().splitlines()
        first_line = version[0] if version else "(unknown)"
        print(f"[{GUARD_NAME}] using {BINARY} {first_line}", file=sys.stderr)
    except (subprocess.TimeoutExpired, OSError):
        print(
            f"[{GUARD_NAME}] could not determine {BINARY} version",
            file=sys.stderr,
        )


def _validate(matching: list[str], _all_changed: list[str]) -> list[str]:
    if shutil.which(BINARY) is None:
        print(
            f"[{GUARD_NAME}] {BINARY} not found on PATH; "
            f"allowing push (fail-open)",
            file=sys.stderr,
        )
        return []

    _log_version()

    project_dir = get_project_directory()
    try:
        proc = subprocess.run(
            [BINARY, *matching],
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
