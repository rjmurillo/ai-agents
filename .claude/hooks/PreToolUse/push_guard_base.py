#!/usr/bin/env python3
"""Shared framework for pre-push guard hooks.

Provides one public entry point: :func:`run_guard`. Hooks call it with a
validator function, the path globs that activate them, and a short name
used in log lines and error codes. The framework owns:

- bootstrap of ``hook_utilities``
- consumer-repo skip
- stdin parsing
- ``git diff --name-only @{push}..HEAD`` with ``origin/main...HEAD``
  fallback
- glob filtering (single-segment via fnmatch, multi-segment via prefix
  plus suffix string check; see issue 1884 pre-mortem R-E)
- structured stdout block on violation
- fail-open on infrastructure errors

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (no matching files, validator clean, or infra fallback)
    2 = Block (validator returned violations)
"""

from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

# Bootstrap: find lib directory via env var or manifest walk-up.
# CLAUDE_PLUGIN_ROOT honored when set; otherwise walk up from __file__
# looking for .claude-plugin/plugin.json (the plugin marker). Sibling
# lib/ is the plugin's lib dir. Layout-independent: works in source
# tree (.claude/) and in the deeper src/<provider>/hooks/<event>/ copy.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _cur = Path(__file__).resolve().parent
    _lib_dir = None
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir} (CLAUDE_PLUGIN_ROOT={_plugin_root!r})", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import get_project_directory  # noqa: E402
from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402

GIT_DIFF_TIMEOUT = 10


def _match_glob(path: str, pattern: str) -> bool:
    """Match path against a glob pattern.

    Uses fnmatch for single-segment patterns. Multi-segment patterns
    (those containing /) use a prefix+suffix string check because
    fnmatch and pathlib.match do not anchor * to a single path segment.
    See issue 1884 pre-mortem R-E.
    """
    if "/" not in pattern:
        return fnmatch.fnmatch(path, pattern)
    star_count = pattern.count("*")
    if star_count != 1:
        return fnmatch.fnmatch(path, pattern)
    prefix, suffix = pattern.split("*", 1)
    if not path.startswith(prefix):
        return False
    if not path.endswith(suffix):
        return False
    middle = path[len(prefix):len(path) - len(suffix)] if suffix else path[len(prefix):]
    if "/" in middle:
        return False
    return True


def _filter_by_globs(paths: list[str], globs: list[str]) -> list[str]:
    matched: list[str] = []
    for path in paths:
        for pattern in globs:
            if _match_glob(path, pattern):
                matched.append(path)
                break
    return matched


def _run_git_diff(args: list[str], cwd: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GIT_DIFF_TIMEOUT,
            shell=False,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return proc.returncode, proc.stdout


def _changed_files(cwd: str) -> list[str] | None:
    """Return list of files changed vs upstream, or None on infra failure."""
    rc, out = _run_git_diff(
        ["git", "diff", "--name-only", "@{push}..HEAD"],
        cwd=cwd,
    )
    if rc == 0 and out.strip():
        return [line for line in out.splitlines() if line.strip()]
    rc2, out2 = _run_git_diff(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=cwd,
    )
    if rc2 == 0 and out2.strip():
        return [line for line in out2.splitlines() if line.strip()]
    return None


def _read_stdin_command() -> str | None:
    if sys.stdin.isatty():
        return None
    raw = sys.stdin.read()
    if not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return None
    return command


def _emit_violations(name: str, violations: list[str]) -> None:
    code = name.upper().replace("-", "_")
    header = f"\n## BLOCKED [E_{code}]: {name}\n"
    body = "\n".join(violations)
    footer = "\nFix and re-push.\n"
    print(f"{header}\n{body}\n{footer}")
    print(
        f"[E_{code}] {name} blocked: {len(violations)} violation(s)",
        file=sys.stderr,
    )


def run_guard(
    validator_fn: Callable[[list[str], list[str]], list[str]],
    globs: list[str],
    name: str,
) -> int:
    """Execute a pre-push guard.

    Args:
        validator_fn: Called as ``validator_fn(matching_files, all_changed)``.
            Returns a list of violation lines. Empty list means clean.
        globs: Path patterns that activate the validator.
        name: Short guard name. Becomes ``E_<NAME_UPPER>`` in error code.

    Returns:
        Exit code: 0 to allow, 2 to block.
    """
    if skip_if_consumer_repo(name):
        return 0
    try:
        command = _read_stdin_command()
        if command is None:
            return 0

        project_dir = get_project_directory()
        all_changed = _changed_files(project_dir)
        if all_changed is None:
            print(
                f"[{name}] git diff produced no upstream comparison; "
                f"allowing push (fail-open).",
                file=sys.stderr,
            )
            return 0

        matching = _filter_by_globs(all_changed, globs)
        if not matching:
            return 0

        violations = validator_fn(matching, all_changed)
        if not violations:
            return 0

        _emit_violations(name, violations)
        return 2

    except Exception as exc:
        print(f"{name} guard error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0


def main() -> int:
    """Entry point when invoked directly.

    The base module has no validator of its own; running it without a
    concrete guard is a misconfiguration. Fail-open with a stderr note.
    """
    print(
        "push_guard_base.py is a framework module; invoke a concrete guard "
        "instead. Allowing push (fail-open).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
