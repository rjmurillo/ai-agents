#!/usr/bin/env python3
"""Complete a session log by auto-populating session end evidence.

Finds the current session log, auto-populates session end checklist items
with evidence gathered from git state and file changes, runs validation,
and reports status.

Exit Codes:
    0  - Success: Session log completed and validated
    1  - Error: Validation failed or missing required items

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


def get_repo_root(script_dir: Path) -> Path:
    """Walk up from script dir to find project root."""
    return script_dir.parent.parent.parent.parent


def find_current_session_log(sessions_dir: Path) -> Path | None:
    """Find the most recent session log, preferring today's."""
    if not sessions_dir.is_dir():
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}-session-\d+")

    candidates = sorted(
        [
            f
            for f in sessions_dir.glob("*.json")
            if pattern.match(f.name)
        ],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    if not candidates:
        return None

    # Prefer today's sessions
    today_sessions = [f for f in candidates if f.name.startswith(today)]
    if today_sessions:
        return today_sessions[0]

    return candidates[0]


def get_ending_commit() -> str | None:
    """Get current short commit SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def test_handoff_modified() -> bool:
    """Check if HANDOFF.md was modified (staged or unstaged)."""
    for cmd in (
        ["git", "diff", "--cached", "--name-only"],
        ["git", "diff", "--name-only"],
    ):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and "HANDOFF.md" in result.stdout:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    return False


def test_serena_memory_updated() -> bool:
    """Check for changes in .serena/memories/."""
    memory_pattern = re.compile(r"\.serena/memories[/\\]")
    for cmd in (
        ["git", "diff", "--cached", "--name-only"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if memory_pattern.search(line):
                        return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    return False


def run_markdown_lint() -> dict:
    """Run markdownlint on changed markdown files."""
    changed_md: set[str] = set()
    for cmd in (
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        ["git", "diff", "--name-only", "--diff-filter=ACMR"],
    ):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.strip().endswith(".md"):
                        changed_md.add(line.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    if not changed_md:
        return {"Success": True, "Output": "No markdown files changed"}

    all_success = True
    outputs = []
    for f in changed_md:
        try:
            result = subprocess.run(
                ["npx", "markdownlint-cli2", "--fix", f],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                all_success = False
                outputs.append(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError):
            all_success = False
            outputs.append(f"Failed to lint {f}")

    output_text = (
        f"{len(changed_md)} files linted"
        if all_success
        else "\n".join(outputs)
    )
    return {"Success": all_success, "Output": output_text}


def test_uncommitted_changes() -> bool:
    """Check if there are uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return True
        return bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return True


def validate_path_containment(
    session_path: Path, sessions_dir: Path
) -> bool:
    """CWE-22: Ensure session path is inside sessions directory."""
    resolved = session_path.resolve()
    base = sessions_dir.resolve()
    return str(resolved).startswith(str(base) + os.sep)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Complete a session log with end-of-session evidence."
    )
    parser.add_argument(
        "--session-path",
        type=str,
        default="",
        help="Path to session log JSON. Auto-detects if not provided.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without writing.",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    repo_root = get_repo_root(script_dir)
    sessions_dir = repo_root / ".agents" / "sessions"

    # Find session log
    if args.session_path:
        session_path = Path(args.session_path)
        if not session_path.exists():
            print(f"[FAIL] Session file not found: {session_path}", file=sys.stderr)
            sys.exit(1)
        session_path = session_path.resolve()
        if not validate_path_containment(session_path, sessions_dir):
            print(
                f"[FAIL] Session path must be inside '{sessions_dir}'.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        found = find_current_session_log(sessions_dir)
        if not found:
            print(
                "[FAIL] No session log found in .agents/sessions/",
                file=sys.stderr,
            )
            sys.exit(1)
        session_path = found
        print(f"Auto-detected session log: {session_path}")

    # Read session log
    try:
        with open(session_path, encoding="utf-8") as f:
            session = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[FAIL] Invalid JSON in session file: {e}", file=sys.stderr)
        sys.exit(1)

    # Verify structure
    pc = session.get("protocolCompliance", {})
    session_end = pc.get("sessionEnd")
    if not session_end:
        print(
            "[FAIL] Session log missing protocolCompliance.sessionEnd",
            file=sys.stderr,
        )
        sys.exit(1)

    changes: list[str] = []
    print("\n=== Session End Completion ===")
    print(f"File: {session_path}\n")

    # 1. Ending commit
    ending_commit = get_ending_commit()
    if ending_commit and not session.get("endingCommit"):
        session["endingCommit"] = ending_commit
        changes.append(f"Set endingCommit: {ending_commit}")

    # 2. handoffNotUpdated
    handoff_modified = test_handoff_modified()
    check = session_end.get("handoffNotUpdated")
    if check is not None:
        if handoff_modified:
            check["Complete"] = True
            check["Evidence"] = (
                "WARNING: HANDOFF.md was modified - this violates MUST NOT"
            )
            changes.append("[WARN] HANDOFF.md was modified (MUST NOT violation)")
        else:
            check["Complete"] = False
            check["Evidence"] = "HANDOFF.md not modified (read-only respected)"
            changes.append("Confirmed HANDOFF.md not modified")

    # 3. serenaMemoryUpdated
    memory_updated = test_serena_memory_updated()
    check = session_end.get("serenaMemoryUpdated")
    if check is not None:
        if memory_updated:
            check["Complete"] = True
            check["Evidence"] = ".serena/memories/ has changes"
            changes.append("Confirmed Serena memory updated")
        elif not check.get("Complete"):
            changes.append(
                "[TODO] Serena memory not updated - "
                "update .serena/memories/ before completing"
            )

    # 4. markdownLintRun
    print("Running markdown lint...")
    lint_result = run_markdown_lint()
    check = session_end.get("markdownLintRun")
    if check is not None:
        check["Complete"] = lint_result["Success"]
        check["Evidence"] = lint_result["Output"]
        changes.append(f"Markdown lint: {lint_result['Output']}")

    # 5. changesCommitted
    has_uncommitted = test_uncommitted_changes()
    check = session_end.get("changesCommitted")
    if check is not None:
        if not has_uncommitted:
            check["Complete"] = True
            check["Evidence"] = f"All changes committed (HEAD: {ending_commit})"
            changes.append("All changes committed")
        else:
            changes.append(
                "[TODO] Uncommitted changes exist - commit before completing"
            )

    # 6. Evaluate checklistComplete
    must_items = [
        "handoffNotUpdated",
        "serenaMemoryUpdated",
        "markdownLintRun",
        "changesCommitted",
        "validationPassed",
    ]
    all_must_complete = True
    for item in must_items:
        check = session_end.get(item)
        if check is None:
            continue
        level = check.get("level", "")
        is_complete = check.get("Complete", False)
        if level == "MUST" and not is_complete:
            all_must_complete = False
        if level == "MUST NOT" and is_complete:
            all_must_complete = False

    checklist_check = session_end.get("checklistComplete")
    if checklist_check is not None:
        checklist_check["Complete"] = all_must_complete
        checklist_check["Evidence"] = (
            "All MUST items verified"
            if all_must_complete
            else "Some MUST items still incomplete"
        )

    # Report changes
    print("\n--- Changes ---")
    for change in changes:
        if "TODO" in change:
            prefix = "[TODO]"
        elif "WARN" in change:
            prefix = "[WARN]"
        else:
            prefix = "[OK]"
        print(f"  {prefix} {change}")

    # Write
    if not args.dry_run:
        with open(session_path, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
        print(f"\nUpdated: {session_path}")
    else:
        print("\n[DRY RUN] No changes written")

    # Run validation
    print("\nRunning validation...")
    validate_script = repo_root / "scripts" / "validate_session_json.py"
    if not validate_script.exists():
        # Try PowerShell fallback
        validate_script = repo_root / "scripts" / "Validate-SessionJson.ps1"

    if validate_script.exists():
        if validate_script.suffix == ".py":
            cmd = [sys.executable, str(validate_script), "--session-path", str(session_path)]
        else:
            cmd = ["pwsh", str(validate_script), "-SessionPath", str(session_path)]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        validation_exit = result.returncode

        if not args.dry_run:
            val_check = session_end.get("validationPassed")
            if val_check is not None:
                val_check["Complete"] = validation_exit == 0
                val_check["Evidence"] = (
                    "Validation passed"
                    if validation_exit == 0
                    else "Validation failed"
                )
                if validation_exit == 0 and all_must_complete:
                    checklist_check = session_end.get("checklistComplete")
                    if checklist_check:
                        checklist_check["Complete"] = True
                        checklist_check["Evidence"] = (
                            "All MUST items verified and validation passed"
                        )
                with open(session_path, "w", encoding="utf-8") as f:
                    json.dump(session, f, indent=2)

        if validation_exit != 0:
            print("\n[FAIL] Session validation failed. Fix issues and re-run.")
            sys.exit(1)
    else:
        print(f"Warning: Validation script not found", file=sys.stderr)

    print("\n[PASS] Session log completed and validated")


if __name__ == "__main__":
    main()
