#!/usr/bin/env python3
"""Block commits and pushes when the session branch differs from git.

Canonical source:
`.claude/hooks/PreToolUse/invoke_branch_context_guard.py`

Verbatim check:

    if current_branch != session_branch:
        write_block_response(
            f"Branch mismatch: current='{current_branch}', session='{session_branch}'"
        )
        return 2

Stricter/looser/different than canonical:
This git-hook helper receives no Claude tool payload and writes diagnostics to
stderr instead of a Claude JSON decision. Missing logs, missing branch fields,
detached HEAD, and infrastructure errors still fail open with exit 0.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

_GIT_TIMEOUT_SECONDS = 10


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=repo_root,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None


def _repo_root() -> Path | None:
    result = _run_git(Path.cwd(), "rev-parse", "--show-toplevel")
    if result is None or result.returncode != 0:
        return None
    root = result.stdout.strip()
    return Path(root) if root else None


def _current_branch(repo_root: Path) -> str | None:
    result = _run_git(repo_root, "branch", "--show-current")
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _today_session_log(repo_root: Path) -> Path | None:
    sessions_dir = repo_root / ".agents" / "sessions"
    if not sessions_dir.is_dir():
        return None
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    newest: tuple[float, Path] | None = None
    try:
        candidates = sessions_dir.glob(f"{today}-session-*.json")
        for candidate in candidates:
            try:
                item = (candidate.stat().st_mtime, candidate)
            except OSError:
                continue
            if newest is None or item[0] > newest[0]:
                newest = item
    except OSError:
        return None
    return newest[1] if newest else None


def _session_branch(session_log: Path) -> str | None:
    try:
        data = json.loads(session_log.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    session = data.get("session")
    containers = (session, data) if isinstance(session, dict) else (data,)
    for container in containers:
        branch = container.get("branch")
        if isinstance(branch, str) and branch:
            return branch
    return None


def check_branch_context(repo_root: Path) -> int:
    current_branch = _current_branch(repo_root)
    if current_branch is None:
        return 0
    session_log = _today_session_log(repo_root)
    if session_log is None:
        return 0
    session_branch = _session_branch(session_log)
    if session_branch is None:
        return 0
    if current_branch != session_branch:
        print(
            "ERROR: branch context mismatch: "
            f"current='{current_branch}', session='{session_branch}'",
            file=sys.stderr,
        )
        print(f"  Session log: {session_log}", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    repo_root = _repo_root()
    return check_branch_context(repo_root) if repo_root is not None else 0


if __name__ == "__main__":
    sys.exit(main())
