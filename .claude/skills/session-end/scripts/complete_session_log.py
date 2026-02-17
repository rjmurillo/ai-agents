#!/usr/bin/env python3
"""Complete a session log by auto-populating session end evidence and validating.

Finds the current session log, auto-populates session end checklist items
with evidence gathered from git state and file changes, runs validation,
and reports status.

Exit codes follow ADR-035:
    0 - Success
    1 - Error: Validation failed or missing required items
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Complete and validate a session log.",
    )
    parser.add_argument(
        "--session-path", default="",
        help="Path to session log JSON. Auto-detects most recent if not provided.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would change without writing to the file.",
    )
    return parser


def _get_repo_root() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        return os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."),
        )
    return result.stdout.strip()


def _find_current_session_log(sessions_dir: str) -> str | None:
    """Find the most recent session log, preferring today's sessions."""
    from datetime import datetime
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    if not os.path.isdir(sessions_dir):
        return None

    candidates = []
    for name in os.listdir(sessions_dir):
        if name.endswith(".json") and re.match(r"\d{4}-\d{2}-\d{2}-session-\d+", name):
            full = os.path.join(sessions_dir, name)
            candidates.append((os.path.getmtime(full), full, name))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)

    # Prefer today's sessions
    for _, full, name in candidates:
        if name.startswith(today):
            return full

    return candidates[0][1]


def _get_ending_commit() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _test_handoff_modified() -> bool:
    for cmd in [["git", "diff", "--cached", "--name-only"], ["git", "diff", "--name-only"]]:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode == 0 and "HANDOFF.md" in result.stdout:
            return True
    return False


def _test_serena_memory_updated() -> bool:
    for cmd in [
        ["git", "diff", "--cached", "--name-only"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith(".serena/memories"):
                    return True
    return False


def _run_markdown_lint() -> tuple[bool, str]:
    """Run markdownlint on changed markdown files. Returns (success, message)."""
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    unstaged = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR"],
        capture_output=True, text=True, timeout=10, check=False,
    )

    md_files = set()
    for output in [staged.stdout, unstaged.stdout]:
        for line in output.splitlines():
            if line.strip().endswith(".md"):
                md_files.add(line.strip())

    if not md_files:
        return True, "No markdown files changed"

    all_success = True
    errors = []
    for f in md_files:
        result = subprocess.run(
            ["npx", "markdownlint-cli2", "--fix", "--", f],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode != 0:
            all_success = False
            errors.append(result.stdout.strip() or result.stderr.strip())

    if all_success:
        return True, f"{len(md_files)} files linted"
    return False, "\n".join(errors)


def _test_uncommitted_changes() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        return True
    return bool(result.stdout.strip())


def _validate_path_containment(session_path: str, sessions_dir: str) -> str | None:
    """Validate session path is inside sessions directory. Returns resolved path or None."""
    try:
        resolved = os.path.realpath(session_path)
        base = os.path.realpath(sessions_dir) + os.sep
        if not resolved.startswith(base):
            return None
        return resolved
    except (OSError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = _get_repo_root()

    if not os.path.isdir(os.path.join(repo_root, ".agents")):
        print("[SKIP] .agents/ not found. Requires project scaffolding.")
        return 0

    sessions_dir = os.path.join(repo_root, ".agents", "sessions")

    # Find session log
    session_path = args.session_path
    if not session_path:
        session_path = _find_current_session_log(sessions_dir)
        if not session_path:
            print("[FAIL] No session log found in .agents/sessions/", file=sys.stderr)
            return 1
        print(f"Auto-detected session log: {session_path}", file=sys.stderr)
    else:
        if not os.path.isfile(session_path):
            print(f"[FAIL] Session file not found: {session_path}", file=sys.stderr)
            return 1
        resolved = _validate_path_containment(session_path, sessions_dir)
        if resolved is None:
            print(f"[FAIL] Session path must be inside '{sessions_dir}'.", file=sys.stderr)
            return 1
        session_path = resolved

    # Read session log
    try:
        with open(session_path, encoding="utf-8") as f:
            session = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[FAIL] Invalid JSON in session file: {session_path}", file=sys.stderr)
        print(f"  Error: {exc}", file=sys.stderr)
        return 1

    # Verify structure
    pc = session.get("protocolCompliance", {})
    session_end = pc.get("sessionEnd")
    if session_end is None:
        print("[FAIL] Session log missing protocolCompliance.sessionEnd section", file=sys.stderr)
        return 1

    changes: list[str] = []
    print("", file=sys.stderr)
    print("=== Session End Completion ===", file=sys.stderr)
    print(f"File: {session_path}", file=sys.stderr)
    print("", file=sys.stderr)

    # 1. Ending commit
    ending_commit = _get_ending_commit()
    if ending_commit and not session.get("endingCommit"):
        session["endingCommit"] = ending_commit
        changes.append(f"Set endingCommit: {ending_commit}")

    # 2. handoffNotUpdated (MUST NOT)
    handoff_modified = _test_handoff_modified()
    if "handoffNotUpdated" in session_end:
        check = session_end["handoffNotUpdated"]
        if handoff_modified:
            check["Complete"] = True
            check["Evidence"] = "WARNING: HANDOFF.md was modified - this violates MUST NOT"
            changes.append("[WARN] HANDOFF.md was modified (MUST NOT violation)")
        else:
            check["Complete"] = False
            check["Evidence"] = "HANDOFF.md not modified (read-only respected)"
            changes.append("Confirmed HANDOFF.md not modified")

    # 3. serenaMemoryUpdated
    memory_updated = _test_serena_memory_updated()
    if "serenaMemoryUpdated" in session_end:
        check = session_end["serenaMemoryUpdated"]
        if memory_updated:
            check["Complete"] = True
            check["Evidence"] = ".serena/memories/ has changes"
            changes.append("Confirmed Serena memory updated")
        elif not check.get("Complete"):
            changes.append(
                "[TODO] Serena memory not updated"
                " - update .serena/memories/ before completing"
            )

    # 4. markdownLintRun
    print("Running markdown lint...", file=sys.stderr)
    lint_success, lint_output = _run_markdown_lint()
    if "markdownLintRun" in session_end:
        check = session_end["markdownLintRun"]
        check["Complete"] = lint_success
        check["Evidence"] = lint_output
        changes.append(f"Markdown lint: {lint_output}")

    # 5. changesCommitted
    has_uncommitted = _test_uncommitted_changes()
    if "changesCommitted" in session_end:
        check = session_end["changesCommitted"]
        if not has_uncommitted:
            check["Complete"] = True
            check["Evidence"] = f"All changes committed (HEAD: {ending_commit})"
            changes.append("All changes committed")
        else:
            changes.append("[TODO] Uncommitted changes exist - commit before completing")

    # 6. checklistComplete - evaluate after all others
    must_items = ["handoffNotUpdated", "serenaMemoryUpdated", "markdownLintRun",
                  "changesCommitted", "validationPassed"]
    all_must_complete = True
    for item in must_items:
        if item in session_end:
            check = session_end[item]
            level = check.get("level", "")
            complete = check.get("Complete", False)
            if level == "MUST" and not complete:
                all_must_complete = False
            if level == "MUST NOT" and complete:
                all_must_complete = False

    if "checklistComplete" in session_end:
        check = session_end["checklistComplete"]
        check["Complete"] = all_must_complete
        if all_must_complete:
            check["Evidence"] = "All MUST items verified"
        else:
            check["Evidence"] = "Some MUST items still incomplete"

    # Report changes
    print("", file=sys.stderr)
    print("--- Changes ---", file=sys.stderr)
    for change in changes:
        print(f"  {change}", file=sys.stderr)

    # Write updated session log
    if not args.dry_run:
        with open(session_path, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
        print("", file=sys.stderr)
        print(f"Updated: {session_path}", file=sys.stderr)
    else:
        print("", file=sys.stderr)
        print("[DRY RUN] No changes written", file=sys.stderr)

    # Run validation
    print("", file=sys.stderr)
    print("Running validation...", file=sys.stderr)
    validate_script = os.path.join(repo_root, "scripts", "validate_session_json.py")

    if os.path.isfile(validate_script):
        result = subprocess.run(
            [sys.executable, validate_script, session_path],
            capture_output=False, timeout=60, check=False,
        )
        validation_exit_code = result.returncode

        if not args.dry_run and "validationPassed" in session_end:
            check = session_end["validationPassed"]
            check["Complete"] = validation_exit_code == 0
            check["Evidence"] = (
                "validate_session_json.py passed" if validation_exit_code == 0
                else "validate_session_json.py failed"
            )

            if validation_exit_code == 0 and all_must_complete:
                session_end["checklistComplete"]["Complete"] = True
                session_end["checklistComplete"]["Evidence"] = (
                    "All MUST items verified and validation passed"
                )

            with open(session_path, "w", encoding="utf-8") as f:
                json.dump(session, f, indent=2)

        if validation_exit_code != 0:
            print("", file=sys.stderr)
            print("[FAIL] Session validation failed. Fix issues above and re-run.", file=sys.stderr)
            return 1
    else:
        print(f"WARNING: Validation script not found: {validate_script}", file=sys.stderr)

    print("", file=sys.stderr)
    print("[PASS] Session log completed and validated", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
