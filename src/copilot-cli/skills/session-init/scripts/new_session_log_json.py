#!/usr/bin/env python3
"""Create a new session log in JSON format (simplified version).

This is a lightweight alternative to new_session_log.py that creates
session JSON without full validation pipeline integration.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Config / file I/O error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_WORKSPACE = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")),
)
_SESSION_INIT_DIR = os.path.join(os.path.dirname(__file__), "..")
if _SESSION_INIT_DIR not in sys.path:
    sys.path.insert(0, _SESSION_INIT_DIR)


def _resolve_paths_lib_dir() -> str:
    """Resolve the vendor-portable path-helper lib directory (Issue #2050)."""
    plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        lib_dir = Path(plugin_root).expanduser().resolve() / "lib"
        if not lib_dir.is_dir():
            print(f"Plugin lib directory not found: {lib_dir}", file=sys.stderr)
            sys.exit(2)
        return str(lib_dir)
    candidates: list[Path] = []
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if workspace:
        candidates.append(Path(workspace).expanduser().resolve() / ".claude" / "lib")
    candidates.append(Path(__file__).resolve().parents[3] / "lib")
    for lib_dir in candidates:
        if lib_dir.is_dir():
            return str(lib_dir)
    checked = ", ".join(str(candidate) for candidate in candidates)
    print(f"Plugin lib directory not found. Checked: {checked}", file=sys.stderr)
    sys.exit(2)


_LIB_DIR = _resolve_paths_lib_dir()
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from paths import resolve_artifact_root  # noqa: E402
from session_init.session_structure import build_session_log  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a new session log in JSON format.",
    )
    parser.add_argument(
        "--session-number",
        type=int,
        default=0,
        help="Session number. Auto-detects from existing files if not provided.",
    )
    parser.add_argument(
        "--objective",
        default="",
        help="Session objective description.",
    )
    parser.add_argument(
        "--trace-id",
        default="",
        help="Trace correlation ID (UUID) for multi-agent execution graphs.",
    )
    parser.add_argument(
        "--parent-session-id",
        default="",
        help="Parent session identifier (YYYY-MM-DD-session-N) for call graph reconstruction.",
    )
    return parser


def _get_branch() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _get_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _get_repo_root() -> str:
    # Use --show-toplevel, not --git-common-dir. In a LINKED worktree the
    # common dir is the MAIN checkout's shared .git, so dirname(common-dir)
    # is the main checkout, not this worktree. --show-toplevel returns the
    # current worktree root in every layout (#2375).
    # Canonical reference: scripts/github_core/repo.py::get_repo_root.
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return _WORKSPACE
    raw = result.stdout.strip()
    if not raw:
        return _WORKSPACE
    toplevel = Path(raw)
    if not toplevel.is_absolute():
        toplevel = (Path.cwd() / toplevel).resolve()
    else:
        toplevel = toplevel.resolve()
    return str(toplevel)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    repo_root = _get_repo_root()

    sessions_dir = str(resolve_artifact_root("sessions", base=repo_root))

    current_date = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    branch = _get_branch()
    commit = _get_commit()

    # Auto-detect session number
    session_number = args.session_number
    if session_number == 0:
        max_num = 0
        for name in os.listdir(sessions_dir) if os.path.isdir(sessions_dir) else []:
            m = re.search(r"session-(\d+)", name)
            if m and name.endswith(".json"):
                max_num = max(max_num, int(m.group(1)))
        session_number = max_num + 1 if max_num else 1

    # CWE-400: Reject session number jumps larger than 10 above max existing
    max_existing = 0
    found_existing = False
    for name in os.listdir(sessions_dir) if os.path.isdir(sessions_dir) else []:
        m = re.search(r"session-(\d+)", name)
        if m and name.endswith(".json"):
            max_existing = max(max_existing, int(m.group(1)))
            found_existing = True
    if found_existing and session_number > max_existing + 10:
        print(
            f"ERROR: Session number {session_number} exceeds ceiling "
            f"(max existing: {max_existing}, ceiling: {max_existing + 10}).",
            file=sys.stderr,
        )
        return 1

    session: dict[str, Any] = build_session_log(
        branch=branch,
        commit=commit,
        session_number=session_number,
        objective=args.objective,
        current_date=current_date,
        trace_id=args.trace_id,
        parent_session_id=args.parent_session_id,
    )

    # Atomic file creation with collision retry (CWE-362)
    json_content = json.dumps(session, indent=2) + "\n"
    max_retries = 5
    created = False
    filepath = ""

    for retry in range(max_retries):
        filename = f"{current_date}-session-{session_number}.json"
        filepath = os.path.join(sessions_dir, filename)

        try:
            fd = os.open(filepath, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, json_content.encode("utf-8"))
            finally:
                os.close(fd)
            created = True
            break
        except FileExistsError:
            if retry < max_retries - 1:
                print(
                    f"WARNING: Session {session_number} already exists, "
                    f"trying {session_number + 1}",
                    file=sys.stderr,
                )
                session_number += 1
                session["session"]["number"] = session_number
                json_content = json.dumps(session, indent=2) + "\n"
            else:
                raise

    if not created:
        print(
            f"ERROR: Failed to create session log after {max_retries} attempts.",
            file=sys.stderr,
        )
        return 2

    print(f"Created: {filepath}", file=sys.stderr)
    print(f"Session: {session_number}", file=sys.stderr)
    print(f"Branch: {branch}", file=sys.stderr)
    print(f"Commit: {commit}", file=sys.stderr)

    # Output path on stdout for callers
    print(filepath)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
