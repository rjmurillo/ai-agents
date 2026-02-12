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

_WORKSPACE = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a new session log in JSON format.",
    )
    parser.add_argument(
        "--session-number", type=int, default=0,
        help="Session number. Auto-detects from existing files if not provided.",
    )
    parser.add_argument(
        "--objective", default="",
        help="Session objective description.",
    )
    return parser


def _get_branch() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _get_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _get_repo_root() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        return _WORKSPACE
    return result.stdout.strip() or _WORKSPACE


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    repo_root = _get_repo_root()
    sessions_dir = os.path.join(repo_root, ".agents", "sessions")
    os.makedirs(sessions_dir, exist_ok=True)

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

    objective = args.objective
    not_on_main = branch not in ("main", "master")

    session = {
        "session": {
            "number": session_number,
            "date": current_date,
            "branch": branch,
            "startingCommit": commit,
            "objective": objective if objective else "[TODO: Describe objective]",
        },
        "protocolCompliance": {
            "sessionStart": {
                "serenaActivated": {"level": "MUST", "Complete": False, "Evidence": ""},
                "serenaInstructions": {"level": "MUST", "Complete": False, "Evidence": ""},
                "handoffRead": {"level": "MUST", "Complete": False, "Evidence": ""},
                "sessionLogCreated": {"level": "MUST", "Complete": True, "Evidence": "This file"},
                "skillScriptsListed": {"level": "MUST", "Complete": False, "Evidence": ""},
                "usageMandatoryRead": {"level": "MUST", "Complete": False, "Evidence": ""},
                "constraintsRead": {"level": "MUST", "Complete": False, "Evidence": ""},
                "memoriesLoaded": {"level": "MUST", "Complete": False, "Evidence": ""},
                "branchVerified": {"level": "MUST", "Complete": True, "Evidence": branch},
                "notOnMain": {"level": "MUST", "Complete": not_on_main, "Evidence": f"On {branch}"},
                "gitStatusVerified": {"level": "SHOULD", "Complete": False, "Evidence": ""},
                "startingCommitNoted": {"level": "SHOULD", "Complete": True, "Evidence": commit},
            },
            "sessionEnd": {
                "checklistComplete": {"level": "MUST", "Complete": False, "Evidence": ""},
                "handoffNotUpdated": {"level": "MUST NOT", "Complete": False, "Evidence": ""},
                "serenaMemoryUpdated": {"level": "MUST", "Complete": False, "Evidence": ""},
                "markdownLintRun": {"level": "MUST", "Complete": False, "Evidence": ""},
                "changesCommitted": {"level": "MUST", "Complete": False, "Evidence": ""},
                "validationPassed": {"level": "MUST", "Complete": False, "Evidence": ""},
                "tasksUpdated": {"level": "SHOULD", "Complete": False, "Evidence": ""},
                "retrospectiveInvoked": {"level": "SHOULD", "Complete": False, "Evidence": ""},
            },
        },
        "workLog": [],
        "endingCommit": "",
        "nextSteps": [],
    }

    # Atomic file creation with collision retry (CWE-362)
    json_content = json.dumps(session, indent=2)
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
                json_content = json.dumps(session, indent=2)
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
