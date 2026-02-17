#!/usr/bin/env python3
"""Create protocol-compliant JSON session log with verification-based enforcement.

Automates JSON session log creation by:
1. Auto-detecting or accepting session number and objective
2. Detecting date/branch/commit/git status
3. Generating JSON structure with schemaVersion field
4. Writing JSON file to .agents/sessions/
5. Validating with JSON schema + validate_session_json.py
6. Exiting nonzero on validation failure

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Config / file I/O error
    3 - External error
    4 - Validation failed
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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from session_init.git_helpers import get_git_info  # noqa: E402
from session_init.template_helpers import get_descriptive_keywords  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create protocol-compliant JSON session log.",
    )
    parser.add_argument(
        "--session-number", type=int, default=0,
        help="Session number. Auto-detects from existing files if not provided.",
    )
    parser.add_argument(
        "--objective", default="",
        help="Session objective description.",
    )
    parser.add_argument(
        "--skip-validation", action="store_true",
        help="Skip validation after creating session log (testing only).",
    )
    return parser


def _auto_detect_session_number(sessions_dir: str) -> int:
    """Auto-increment session number from latest session in directory."""
    if not os.path.isdir(sessions_dir):
        return 1
    max_num = 0
    for name in os.listdir(sessions_dir):
        m = re.search(r"session-(\d+)", name)
        if m and name.endswith(".json"):
            max_num = max(max_num, int(m.group(1)))
    return max_num + 1 if max_num else 1


def _get_max_existing_session(sessions_dir: str) -> int | None:
    """Get the maximum existing session number."""
    if not os.path.isdir(sessions_dir):
        return None
    max_num = 0
    found = False
    for name in os.listdir(sessions_dir):
        m = re.search(r"session-(\d+)", name)
        if m and name.endswith(".json"):
            max_num = max(max_num, int(m.group(1)))
            found = True
    return max_num if found else None


def _derive_objective(branch: str) -> str:
    """Derive objective from branch name or recent commits."""
    m = re.match(r"^(?:feat|feature|fix|refactor|chore|docs)/(.+)$", branch)
    if m:
        topic = m.group(1).replace("-", " ")
        return f"Work on {topic}"

    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-3"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            first_line = result.stdout.strip().splitlines()[0]
            parts = first_line.split(None, 1)
            if len(parts) == 2:
                return f"Continue: {parts[1].strip()}"
    except Exception:
        pass
    return ""


def _build_session_data(
    git_info: dict[str, str],
    session_number: int,
    objective: str,
    current_date: str,
) -> dict:
    """Build the session JSON data structure."""
    branch = git_info["branch"]
    commit = git_info["commit"]
    not_on_main = branch not in ("main", "master")

    return {
        "session": {
            "number": session_number,
            "date": current_date,
            "branch": branch,
            "startingCommit": commit,
            "objective": objective or "[TODO: Describe objective]",
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


def _write_session_file(
    sessions_dir: str,
    session_data: dict,
    current_date: str,
    objective: str,
) -> tuple[str, int]:
    """Write session JSON file with atomic creation and collision retry.

    Returns (file_path, final_session_number).
    """
    os.makedirs(sessions_dir, exist_ok=True)
    session_number = session_data["session"]["number"]
    max_retries = 5

    for retry in range(max_retries):
        keywords = get_descriptive_keywords(objective)
        suffix = f"-{keywords}" if keywords else ""
        filename = f"{current_date}-session-{session_number}{suffix}.json"
        filepath = os.path.join(sessions_dir, filename)

        try:
            fd = os.open(filepath, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                content = json.dumps(session_data, indent=2)
                os.write(fd, content.encode("utf-8"))
            finally:
                os.close(fd)
            return filepath, session_number
        except FileExistsError:
            if retry < max_retries - 1:
                session_number += 1
                session_data["session"]["number"] = session_number
                print(
                    f"WARNING: Session file collision, retrying with session-{session_number}",
                    file=sys.stderr,
                )
            else:
                raise

    msg = f"Failed to create session log after {max_retries} attempts."
    raise OSError(msg)


def _run_validation(session_log_path: str, repo_root: str) -> bool:
    """Validate session log using validate_session_json.py.

    Returns True if validation passed.
    """
    validation_script = os.path.join(repo_root, "scripts", "validate_session_json.py")
    if not os.path.isfile(validation_script):
        print(
            f"CRITICAL: Validation script not found at: {validation_script}",
            file=sys.stderr,
        )
        return False

    print("Running validation...", file=sys.stderr)
    result = subprocess.run(
        [sys.executable, validation_script, session_log_path],
        capture_output=False,
        timeout=60,
        check=False,
    )
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Phase 1: Get git info
    try:
        git_info = get_git_info()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    repo_root = git_info["repo_root"]

    sessions_dir = os.path.join(repo_root, ".agents", "sessions")
    os.makedirs(sessions_dir, exist_ok=True)
    current_date = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    # Resolve session number
    session_number = args.session_number
    if session_number == 0:
        session_number = _auto_detect_session_number(sessions_dir)

    # CWE-400: Reject session number jumps larger than 10 above max existing
    max_existing = _get_max_existing_session(sessions_dir)
    if max_existing is not None and session_number > max_existing + 10:
        print(
            f"ERROR: Session number {session_number} exceeds ceiling "
            f"(max existing: {max_existing}, ceiling: {max_existing + 10}). "
            f"This prevents DoS via large session numbers.",
            file=sys.stderr,
        )
        return 1

    # Resolve objective
    objective = args.objective
    if not objective:
        objective = _derive_objective(git_info["branch"])

    # Phase 2: Build and write session log
    session_data = _build_session_data(git_info, session_number, objective, current_date)

    try:
        filepath, final_number = _write_session_file(
            sessions_dir, session_data, current_date, objective,
        )
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Created: {filepath}", file=sys.stderr)
    print(f"Session: {final_number}", file=sys.stderr)
    print(f"Branch: {git_info['branch']}", file=sys.stderr)
    print(f"Commit: {git_info['commit']}", file=sys.stderr)

    # Phase 3: Validate
    if not args.skip_validation:
        passed = _run_validation(filepath, repo_root)
        if not passed:
            print(
                f"\nSession log created but validation FAILED.\n"
                f"  File: {filepath}\n"
                f"Fix issues and re-validate:\n"
                f"  python3 scripts/validate_session_json.py \"{filepath}\"",
                file=sys.stderr,
            )
            return 4
    else:
        print("Validation skipped (--skip-validation flag set).", file=sys.stderr)

    # Output the file path on stdout for callers to capture
    print(filepath)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
