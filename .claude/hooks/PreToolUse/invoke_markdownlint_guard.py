#!/usr/bin/env python3
"""Block git push on markdownlint violations in changed .md files.

Thin adapter over :mod:`push_guard_base`. Activates on ``*.md`` files in
the push changeset and runs ``markdownlint-cli2`` against them. Missing
tools, timeouts, invocation failures, and lint violations all block.

Customer value: prevents markdown lint failures from reaching consumer branches.

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (no .md files or markdownlint clean)
    2 = Block (markdownlint unavailable, failed, or reported violations)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from _bootstrap import ensure_plugin_paths

ensure_plugin_paths()

from hook_utilities import get_project_directory  # noqa: E402
from push_guard_base import run_guard  # noqa: E402

GUARD_NAME = "markdown-lint"
BINARY = "markdownlint-cli2"
SUBPROCESS_TIMEOUT = 60
VERSION_TIMEOUT = 5
CONFIG_PATH = Path(__file__).with_name("markdownlint-cli2.yaml")


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _resolve_invocation(project_dir: str) -> list[str] | None:
    """Resolve a global markdownlint executable outside the consumer repository."""
    executable = shutil.which(BINARY)
    if executable is None:
        return None

    unresolved_executable = Path(executable).absolute()
    resolved_executable = Path(executable).resolve()
    resolved_project = Path(project_dir).resolve()
    if _is_within(unresolved_executable, resolved_project):
        return None
    if _is_within(resolved_executable, resolved_project):
        return None

    trusted_roots = []
    for entry in os.get_exec_path():
        root = Path(entry)
        if not root.is_absolute():
            continue
        absolute_root = root.absolute()
        resolved_root = root.resolve()
        if _is_within(absolute_root, resolved_project):
            continue
        if _is_within(resolved_root, resolved_project):
            continue
        trusted_roots.append(absolute_root)

    if unresolved_executable.parent not in trusted_roots:
        return None
    return [str(resolved_executable)]


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


def _lint_markdown_file(
    invocation: list[str],
    project_dir: Path,
    relative_path: str,
) -> list[str]:
    markdown_path = (project_dir / relative_path).resolve()
    if not _is_within(markdown_path, project_dir):
        return [f"{relative_path}: path escapes repository"]
    try:
        markdown = markdown_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"{relative_path}: failed to read: {exc}"]

    try:
        proc = subprocess.run(
            [
                *invocation,
                "--config",
                str(CONFIG_PATH),
                "--no-globs",
                "-",
            ],
            input=markdown,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
            shell=False,
            check=False,
            cwd=CONFIG_PATH.parent,
        )
    except subprocess.TimeoutExpired:
        message = f"{relative_path}: {BINARY} exceeded {SUBPROCESS_TIMEOUT}s"
        print(f"[TIMEOUT] {message}; blocking push", file=sys.stderr)
        return [message]
    except OSError as exc:
        message = f"{relative_path}: {BINARY} failed to invoke: {exc}"
        print(f"[OSError] {message}; blocking push", file=sys.stderr)
        return [message]

    if proc.returncode == 0:
        return []
    diagnostics = [
        line
        for output in (proc.stdout, proc.stderr)
        for line in output.splitlines()
        if line.strip()
    ]
    if not diagnostics:
        diagnostics = [f"{BINARY} exited {proc.returncode} without diagnostics"]
    return [f"{relative_path}: {line}" for line in diagnostics]


def _validate(matching: list[str], _all_changed: list[str]) -> list[str]:
    project_dir = get_project_directory()
    invocation = _resolve_invocation(project_dir)
    if invocation is None:
        message = f"trusted {BINARY} not found outside the repository"
        print(
            f"[{GUARD_NAME}] {message}; blocking push",
            file=sys.stderr,
        )
        return [message]
    if not CONFIG_PATH.is_file():
        message = f"plugin markdownlint config missing: {CONFIG_PATH}"
        print(f"[{GUARD_NAME}] {message}; blocking push", file=sys.stderr)
        return [message]

    _log_version(invocation)

    violations: list[str] = []
    resolved_project = Path(project_dir).resolve()
    for relative_path in matching:
        violations.extend(
            _lint_markdown_file(invocation, resolved_project, relative_path)
        )
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
