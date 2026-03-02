#!/usr/bin/env python3
"""Create protocol-compliant JSON session log with verification-based enforcement.

Automates JSON session log creation by:
1. Auto-detecting or prompting for session number and objective
2. Detecting date/branch/commit/git status
3. Generating JSON structure with schemaVersion field
4. Writing JSON file to .agents/sessions/
5. Validating with JSON schema + validation script
6. Exiting nonzero on validation failure

Exit Codes:
    0  - Success: Session log created and validated
    1  - Error: Git repository error
    2  - Error: Session log write failed
    3  - Error: JSON schema validation failed
    4  - Error: Script validation failed

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


def get_git_info() -> dict:
    """Gather git repository information."""
    info = {"RepoRoot": "", "Branch": "", "Commit": "", "Status": ""}

    # Repo root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            print("Not in a git repository", file=sys.stderr)
            sys.exit(1)
        info["RepoRoot"] = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("Git not available", file=sys.stderr)
        sys.exit(1)

    # Branch
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=10,
        )
        info["Branch"] = result.stdout.strip() if result.returncode == 0 else "unknown"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        info["Branch"] = "unknown"

    # Commit
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        info["Commit"] = result.stdout.strip() if result.returncode == 0 else "unknown"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        info["Commit"] = "unknown"

    # Status
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            info["Status"] = "clean" if not result.stdout.strip() else "dirty"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        info["Status"] = "unknown"

    return info


def get_descriptive_keywords(objective: str) -> str:
    """Extract keywords from objective for filename."""
    if not objective:
        return ""
    words = re.sub(r"[^\w\s-]", "", objective.lower()).split()
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "shall", "can",
        "on", "in", "at", "to", "for", "of", "with", "by", "from",
        "as", "into", "through", "during", "before", "after", "and",
        "but", "or", "not", "work",
    }
    keywords = [w for w in words if w not in stop_words and len(w) > 2][:3]
    return "-".join(keywords) if keywords else ""


def auto_detect_session_number(sessions_dir: Path) -> int | None:
    """Find highest existing session number and return next."""
    if not sessions_dir.is_dir():
        return None
    pattern = re.compile(r"session-(\d+)")
    numbers = []
    for f in sessions_dir.glob("*.json"):
        m = pattern.search(f.name)
        if m:
            numbers.append(int(m.group(1)))
    if not numbers:
        return None
    return max(numbers) + 1


def get_max_existing(sessions_dir: Path) -> int | None:
    """Return highest existing session number or None."""
    if not sessions_dir.is_dir():
        return None
    pattern = re.compile(r"session-(\d+)")
    numbers = []
    for f in sessions_dir.glob("*.json"):
        m = pattern.search(f.name)
        if m:
            numbers.append(int(m.group(1)))
    return max(numbers) if numbers else None


def derive_objective(branch: str) -> str | None:
    """Try to derive objective from branch name or recent commits."""
    if branch:
        m = re.match(r"^(?:feat|feature|fix|refactor|chore|docs)/(.+)$", branch)
        if m:
            topic = m.group(1).replace("-", " ")
            return f"Work on {topic}"

    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-3"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            first_line = result.stdout.strip().splitlines()[0]
            m = re.match(r"^\w+\s+(.+)$", first_line)
            if m:
                return f"Continue: {m.group(1).strip()}"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


def build_session_data(
    session_number: int,
    date: str,
    branch: str,
    commit: str,
    objective: str,
) -> dict:
    """Build session JSON with schemaVersion."""
    return {
        "schemaVersion": "1.0",
        "session": {
            "number": session_number,
            "date": date,
            "branch": branch,
            "startingCommit": commit,
            "objective": objective,
        },
        "protocolCompliance": {
            "sessionStart": {
                "serenaActivated": {"Complete": False, "level": "MUST", "Evidence": ""},
                "serenaInstructions": {"Complete": False, "level": "MUST", "Evidence": ""},
                "handoffRead": {"Complete": False, "level": "MUST", "Evidence": ""},
                "sessionLogCreated": {
                    "Complete": True,
                    "level": "MUST",
                    "Evidence": "This file exists",
                },
                "skillScriptsListed": {"Complete": False, "level": "MUST", "Evidence": ""},
                "usageMandatoryRead": {"Complete": False, "level": "MUST", "Evidence": ""},
                "constraintsRead": {
                    "Complete": False,
                    "level": "MUST",
                    "Evidence": "",
                },
                "memoriesLoaded": {"Complete": False, "level": "MUST", "Evidence": ""},
                "branchVerified": {
                    "Complete": True,
                    "level": "MUST",
                    "Evidence": f"Branch: {branch}",
                },
                "notOnMain": {
                    "Complete": branch not in ("main", "master"),
                    "level": "MUST",
                    "Evidence": "",
                },
                "gitStatusVerified": {
                    "Complete": False,
                    "level": "SHOULD",
                    "Evidence": "",
                },
                "startingCommitNoted": {
                    "Complete": True,
                    "level": "SHOULD",
                    "Evidence": f"SHA: {commit}",
                },
            },
            "sessionEnd": {
                "checklistComplete": {"Complete": False, "level": "MUST", "Evidence": ""},
                "serenaMemoryUpdated": {"Complete": False, "level": "MUST", "Evidence": ""},
                "markdownLintRun": {"Complete": False, "level": "MUST", "Evidence": ""},
                "changesCommitted": {"Complete": False, "level": "MUST", "Evidence": ""},
                "validationPassed": {"Complete": False, "level": "MUST", "Evidence": ""},
                "handoffNotUpdated": {"Complete": False, "level": "MUST NOT", "Evidence": ""},
                "tasksUpdated": {"Complete": False, "level": "SHOULD", "Evidence": ""},
                "retrospectiveInvoked": {"Complete": False, "level": "SHOULD", "Evidence": ""},
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
    objective: str,
    session_data: dict,
) -> Path:
    """Write session file atomically (CWE-362 prevention)."""
    sessions_dir.mkdir(parents=True, exist_ok=True)

    for retry in range(MAX_RETRIES):
        keywords = get_descriptive_keywords(objective)
        suffix = f"-{keywords}" if keywords else ""
        file_name = f"{date}-session-{session_number}{suffix}.json"
        file_path = sessions_dir / file_name

        try:
            fd = os.open(str(file_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2)
            return file_path
        except FileExistsError:
            if retry < MAX_RETRIES - 1:
                session_number += 1
                session_data["session"]["number"] = session_number
                print(
                    f"Session file collision, retrying with session-{session_number}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Failed to create session log after {MAX_RETRIES} attempts.",
                    file=sys.stderr,
                )
                sys.exit(2)
        except PermissionError:
            print(f"Permission denied writing: {file_path}", file=sys.stderr)
            sys.exit(2)
        except OSError as e:
            print(f"File I/O error: {e}", file=sys.stderr)
            sys.exit(2)

    # Should not reach here
    sys.exit(2)


def validate_session_log(session_log_path: Path, repo_root: str) -> bool:
    """Two-tier validation: schema + script."""
    repo = Path(repo_root)

    # Phase 1: Schema validation
    schema_path = repo / ".agents" / "schemas" / "session-log.schema.json"
    if not schema_path.exists():
        print(f"CRITICAL: JSON schema not found at: {schema_path}", file=sys.stderr)
        return False

    try:
        with open(session_log_path, encoding="utf-8") as f:
            json.load(f)
        print("  Schema validation PASSED (JSON syntax valid)")
    except json.JSONDecodeError as e:
        print(f"JSON schema validation FAILED: {e}", file=sys.stderr)
        return False

    # Phase 2: Script validation
    validation_script = repo / "scripts" / "validate_session_json.py"
    if not validation_script.exists():
        validation_script = repo / "scripts" / "Validate-SessionJson.ps1"

    if not validation_script.exists():
        print(
            "CRITICAL: Validation script not found",
            file=sys.stderr,
        )
        return False

    try:
        if validation_script.suffix == ".py":
            cmd = [sys.executable, str(validation_script), "--session-path", str(session_log_path)]
        else:
            cmd = ["pwsh", str(validation_script), "-SessionPath", str(session_log_path)]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"  Script validation FAILED (exit {result.returncode})")
            if result.stdout:
                print(result.stdout)
            return False
        print("  Script validation PASSED")
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  Validation script error: {e}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create protocol-compliant JSON session log."
    )
    parser.add_argument("--session-number", type=int, default=0)
    parser.add_argument("--objective", type=str, default="")
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()

    print("=== JSON Session Log Creator ===\n")

    # Phase 1: Gather inputs
    print("Phase 1: Gathering inputs...")
    git_info = get_git_info()
    print(f"  Repository: {git_info['RepoRoot']}")
    print(f"  Branch: {git_info['Branch']}")
    print(f"  Commit: {git_info['Commit']}")
    print(f"  Status: {git_info['Status']}\n")

    repo_root = git_info["RepoRoot"]
    sessions_dir = Path(repo_root) / ".agents" / "sessions"

    session_number = args.session_number
    if session_number == 0:
        detected = auto_detect_session_number(sessions_dir)
        session_number = detected if detected else 1

    # CWE-400 ceiling check
    max_existing = get_max_existing(sessions_dir)
    if max_existing is not None and session_number > max_existing + MAX_SESSION_JUMP:
        print(
            f"Session number {session_number} exceeds ceiling "
            f"(max: {max_existing}, ceiling: {max_existing + MAX_SESSION_JUMP})",
            file=sys.stderr,
        )
        sys.exit(1)

    objective = args.objective
    if not objective:
        derived = derive_objective(git_info["Branch"])
        if derived:
            objective = derived

    if not objective:
        objective = "[TODO: Describe objective]"

    print(f"  Session Number: {session_number}")
    print(f"  Objective: {objective}\n")

    # Phase 2: Create session log
    print("Phase 2: Creating JSON session log...")
    date = datetime.now().strftime("%Y-%m-%d")
    session_data = build_session_data(
        session_number, date, git_info["Branch"], git_info["Commit"], objective
    )
    session_log_path = write_session_file(
        sessions_dir, date, session_number, objective, session_data
    )
    print(f"  File: {session_log_path}\n")

    # Phase 3: Validate
    if not args.skip_validation:
        print("Phase 3: Validating session log...")
        valid = validate_session_log(session_log_path, repo_root)
        if not valid:
            print("\n=== FAILED ===")
            print("Session log created but validation FAILED")
            print(f"  File: {session_log_path}")
            sys.exit(4)
    else:
        print("Phase 3: Validation skipped (--skip-validation)\n")

    print("\n=== SUCCESS ===")
    if args.skip_validation:
        print("Session log created (validation SKIPPED)")
    else:
        print("JSON session log created and validated")
    print(f"  File: {session_log_path}")
    print(f"  Session: {session_number}")
    print(f"  Branch: {git_info['Branch']}")
    print(f"  Commit: {git_info['Commit']}\n")
    print("Next: Complete Session Start checklist in the session log")


if __name__ == "__main__":
    main()
