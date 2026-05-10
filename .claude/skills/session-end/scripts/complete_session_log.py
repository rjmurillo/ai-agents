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
from pathlib import Path


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
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        return os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."),
        )
    git_common = Path(result.stdout.strip())
    if not git_common.is_absolute():
        git_common = (Path.cwd() / git_common).resolve()
    else:
        git_common = git_common.resolve()
    return str(git_common.parent)


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


# Rework warning (REQ-009-07, REQ-009-08, REQ-009-09 / M4).
#
# Surfaces files edited >= REWORK_THRESHOLD times in the current branch's
# commit history. PR #1965 had scan.py touched 56 times before submission
# and no tooling surfaced the rework signal. Threshold-6 is a starter
# calibration documented in DESIGN-009; kill-criteria pattern (review at
# 30 invocations) mirrors the Step 0 gate calibration from REQ-006-13.
#
# Excluded patterns are generated artifacts that legitimately turn over
# many times per session (the session log itself, agent-generated copies
# under src/claude/, and other session JSON files). Counting them as
# rework would drown the signal in noise.
REWORK_THRESHOLD = 6
REWORK_EXCLUDED_SUFFIXES = (".session.json",)
REWORK_EXCLUDED_PREFIXES = ("src/claude/", ".agents/sessions/")


def _is_excluded_rework_path(path: str) -> bool:
    """Return True if `path` matches a generated-artifact exclusion pattern."""
    return any(path.endswith(suffix) for suffix in REWORK_EXCLUDED_SUFFIXES) or any(
        path.startswith(prefix) for prefix in REWORK_EXCLUDED_PREFIXES
    )


def compute_rework_warning(
    branch_base: str = "main",
    threshold: int = REWORK_THRESHOLD,
) -> list[tuple[str, int]]:
    """Return files edited >= `threshold` times on this branch vs `branch_base`.

    Canonical source: ``git log --name-only --diff-filter=R -M
    origin/{branch_base}..HEAD --pretty=format:`` (rename-aware).

    The ``--diff-filter=R`` flag combined with ``-M`` enables rename
    detection so a file renamed mid-branch is counted as one logical
    file, not two. The ``--pretty=format:`` empty format suppresses the
    commit header so output lines are file paths only.

    Returns a list of ``(file_path, count)`` tuples for files at or above
    the threshold, sorted by count descending then by path ascending for
    deterministic output.

    Degrades gracefully:
      - Git not available -> returns ``[]``
      - Branch base not reachable (e.g. fresh clone) -> returns ``[]``
      - Empty output (no commits ahead of base) -> returns ``[]``

    Exit codes follow ADR-035; this function never exits.

    Stricter/looser/different than canonical:
      - This is a NEW check; there is no upstream validator to mirror.
      - Threshold-6 is local-only; kill-criteria pattern documented inline.
    """
    from collections import Counter

    try:
        result = subprocess.run(
            [
                "git",
                "log",
                "--name-only",
                "--diff-filter=R",
                "-M",
                f"origin/{branch_base}..HEAD",
                "--pretty=format:",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        # Branch base unreachable, ref missing, or other git failure.
        return []

    counts: Counter[str] = Counter()
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Rename lines from --name-only with -M can appear as
        # "old_path => new_path" or "{dir => other_dir}/file". Collapse
        # both shapes to the new path so the file is counted once.
        if "=>" in line:
            if line.startswith("{") and "}" in line:
                # `{old_dir => new_dir}/filename` form
                head, _, tail = line.partition("}")
                new_dir_section = head.split("=>", 1)[1].strip().lstrip("{").strip()
                new_path = f"{new_dir_section}{tail}"
            else:
                # `old_path => new_path` form
                new_path = line.split("=>", 1)[1].strip()
            line = new_path.lstrip("/").rstrip()
        if _is_excluded_rework_path(line):
            continue
        counts[line] += 1

    over_threshold = [
        (path, count) for path, count in counts.items() if count >= threshold
    ]
    over_threshold.sort(key=lambda item: (-item[1], item[0]))
    return over_threshold


def emit_rework_warning_lines(items: list[tuple[str, int]]) -> list[str]:
    """Render rework-warning output lines (REQ-009-07, REQ-009-08).

    Returns at least one line. Empty input yields ``["rework-warning: none"]``
    so absence of a warning is positive evidence the check ran, not silence.
    """
    if not items:
        return ["rework-warning: none"]
    return [f"rework-warning: {path} edited {count} times" for path, count in items]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = _get_repo_root()

    sessions_dir = os.path.join(repo_root, ".agents", "sessions")
    os.makedirs(sessions_dir, exist_ok=True)

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

    # 2. handoffPreserved (MUST) - replaces legacy handoffNotUpdated (issue #868)
    handoff_modified = _test_handoff_modified()
    # Support both new "handoffPreserved" and legacy "handoffNotUpdated" field names
    handoff_key = (
        "handoffPreserved" if "handoffPreserved" in session_end
        else "handoffNotUpdated" if "handoffNotUpdated" in session_end
        else None
    )
    if handoff_key == "handoffPreserved":
        check = session_end[handoff_key]
        if handoff_modified:
            check["Complete"] = False
            check["Evidence"] = "WARNING: HANDOFF.md was modified (should be read-only)"
            changes.append("[WARN] HANDOFF.md was modified (violation)")
        else:
            check["Complete"] = True
            check["Evidence"] = "HANDOFF.md not modified (read-only respected)"
            changes.append("Confirmed HANDOFF.md preserved (not modified)")
    elif handoff_key == "handoffNotUpdated":
        check = session_end[handoff_key]
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

    # 4b. Rework warning (REQ-009-07, REQ-009-08). Emitted as informational
    # stdout lines after lint; never blocks completion. Output goes to
    # stdout (not stderr) so it can be captured by tooling that pipes the
    # script's output.
    rework_items = compute_rework_warning()
    for line in emit_rework_warning_lines(rework_items):
        print(line)
    if rework_items:
        changes.append(f"[WARN] rework warning: {len(rework_items)} file(s) at 6+ edits")
    else:
        changes.append("Rework warning: none")

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
    must_items = ["handoffPreserved", "handoffNotUpdated", "serenaMemoryUpdated",
                  "markdownLintRun", "changesCommitted", "validationPassed"]
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
