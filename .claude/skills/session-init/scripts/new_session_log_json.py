#!/usr/bin/env python3
"""Create a new session log in JSON format.

Auto-detects session number from existing files and gathers git info.
Writes a protocol-compliant JSON session log to .agents/sessions/.

Exit Codes:
    0  - Success: Session log created
    1  - Error: Invalid params or git error
    2  - Error: File write failed

See: ADR-035 Exit Code Standardization
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MAX_SESSION_JUMP = 10
MAX_RETRIES = 5


def get_repo_root(script_dir: Path) -> Path:
    """Walk up from script dir to find project root."""
    return script_dir.parent.parent.parent.parent


def get_sessions_dir(repo_root: Path) -> Path:
    """Return the sessions directory path."""
    return repo_root / ".agents" / "sessions"


def auto_detect_session_number(sessions_dir: Path) -> int:
    """Find the highest existing session number and return next."""
    if not sessions_dir.is_dir():
        return 1
    pattern = re.compile(r"session-(\d+)")
    numbers = []
    for f in sessions_dir.glob("*.json"):
        m = pattern.search(f.name)
        if m:
            numbers.append(int(m.group(1)))
    if not numbers:
        return 1
    return max(numbers) + 1


def get_max_existing(sessions_dir: Path) -> int | None:
    """Return the highest existing session number or None."""
    if not sessions_dir.is_dir():
        return None
    pattern = re.compile(r"session-(\d+)")
    numbers = []
    for f in sessions_dir.glob("*.json"):
        m = pattern.search(f.name)
        if m:
            numbers.append(int(m.group(1)))
    return max(numbers) if numbers else None


def validate_session_ceiling(session_number: int, sessions_dir: Path) -> None:
    """CWE-400: Reject session number jumps larger than 10 above max."""
    max_existing = get_max_existing(sessions_dir)
    if max_existing is not None and session_number > max_existing + MAX_SESSION_JUMP:
        print(
            f"Session number {session_number} exceeds ceiling "
            f"(max existing: {max_existing}, "
            f"ceiling: {max_existing + MAX_SESSION_JUMP}). "
            "This prevents DoS via large session numbers.",
            file=sys.stderr,
        )
        sys.exit(1)


def get_git_branch() -> str:
    """Get current git branch name."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return "unknown"
        branch = result.stdout.strip()
        return branch if branch else "unknown"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


def get_git_commit() -> str:
    """Get current short commit SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return "unknown"
        commit = result.stdout.strip()
        return commit if commit else "unknown"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


def build_session_object(
    session_number: int,
    date: str,
    branch: str,
    commit: str,
    objective: str,
) -> dict:
    """Build the session JSON structure."""
    return {
        "session": {
            "number": session_number,
            "date": date,
            "branch": branch,
            "startingCommit": commit,
            "objective": objective if objective else "[TODO: Describe objective]",
        },
        "protocolCompliance": {
            "sessionStart": {
                "serenaActivated": {
                    "level": "MUST",
                    "Complete": False,
                    "Evidence": "",
                },
                "serenaInstructions": {
                    "level": "MUST",
                    "Complete": False,
                    "Evidence": "",
                },
                "handoffRead": {
                    "level": "MUST",
                    "Complete": False,
                    "Evidence": "",
                },
                "sessionLogCreated": {
                    "level": "MUST",
                    "Complete": True,
                    "Evidence": "This file",
                },
                "skillScriptsListed": {
                    "level": "MUST",
                    "Complete": False,
                    "Evidence": "",
                },
                "usageMandatoryRead": {
                    "level": "MUST",
                    "Complete": False,
                    "Evidence": "",
                },
                "constraintsRead": {
                    "level": "MUST",
                    "Complete": False,
                    "Evidence": "",
                },
                "memoriesLoaded": {
                    "level": "MUST",
                    "Complete": False,
                    "Evidence": "",
                },
                "branchVerified": {
                    "level": "MUST",
                    "Complete": True,
                    "Evidence": branch,
                },
                "notOnMain": {
                    "level": "MUST",
                    "Complete": branch not in ("main", "master"),
                    "Evidence": f"On {branch}",
                },
                "gitStatusVerified": {
                    "level": "SHOULD",
                    "Complete": False,
                    "Evidence": "",
                },
                "startingCommitNoted": {
                    "level": "SHOULD",
                    "Complete": True,
                    "Evidence": commit,
                },
            },
            "sessionEnd": {
                "checklistComplete": {
                    "level": "MUST",
                    "Complete": False,
                    "Evidence": "",
                },
                "handoffNotUpdated": {
                    "level": "MUST NOT",
                    "Complete": False,
                    "Evidence": "",
                },
                "serenaMemoryUpdated": {
                    "level": "MUST",
                    "Complete": False,
                    "Evidence": "",
                },
                "markdownLintRun": {
                    "level": "MUST",
                    "Complete": False,
                    "Evidence": "",
                },
                "changesCommitted": {
                    "level": "MUST",
                    "Complete": False,
                    "Evidence": "",
                },
                "validationPassed": {
                    "level": "MUST",
                    "Complete": False,
                    "Evidence": "",
                },
                "tasksUpdated": {
                    "level": "SHOULD",
                    "Complete": False,
                    "Evidence": "",
                },
                "retrospectiveInvoked": {
                    "level": "SHOULD",
                    "Complete": False,
                    "Evidence": "",
                },
            },
        },
        "workLog": [],
        "endingCommit": "",
        "nextSteps": [],
    }


def write_session_file(
    sessions_dir: Path,
    date: str,
    session_number: int,
    session_data: dict,
) -> Path:
    """Write session file with atomic creation (CWE-362 prevention).

    Returns the path to the created file.
    Retries with incremented session number on collision.
    """
    sessions_dir.mkdir(parents=True, exist_ok=True)

    for retry in range(MAX_RETRIES):
        file_name = f"{date}-session-{session_number}.json"
        file_path = sessions_dir / file_name
        try:
            fd = os.open(
                str(file_path),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o644,
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2)
            return file_path
        except FileExistsError:
            print(
                f"Session {session_number} already exists, "
                f"trying {session_number + 1}",
                file=sys.stderr,
            )
            session_number += 1
            session_data["session"]["number"] = session_number

    print(
        f"Failed to create session log after {MAX_RETRIES} attempts. "
        f"Last tried: session-{session_number}",
        file=sys.stderr,
    )
    sys.exit(2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a new session log in JSON format."
    )
    parser.add_argument(
        "--session-number",
        type=int,
        default=0,
        help="Session number. Auto-detects if not provided.",
    )
    parser.add_argument(
        "--objective",
        type=str,
        default="",
        help="Session objective description.",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    repo_root = get_repo_root(script_dir)
    sessions_dir = get_sessions_dir(repo_root)

    session_number = args.session_number
    if session_number == 0:
        session_number = auto_detect_session_number(sessions_dir)

    validate_session_ceiling(session_number, sessions_dir)

    date = datetime.now().strftime("%Y-%m-%d")
    branch = get_git_branch()
    commit = get_git_commit()

    session_data = build_session_object(
        session_number, date, branch, commit, args.objective
    )

    file_path = write_session_file(sessions_dir, date, session_number, session_data)

    print(f"Created: {file_path}")
    print(f"Session: {session_data['session']['number']}")
    print(f"Branch: {branch}")
    print(f"Commit: {commit}")


if __name__ == "__main__":
    main()
