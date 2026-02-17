#!/usr/bin/env python3
"""Create a GitHub PR with validation guardrails.

Core PR creation logic with validation gates. Can be called by wrappers
or used directly by skills.

Exit codes follow ADR-035:
    0 - Success
    1 - Validation failure
    2 - Usage/environment error
    3 - External error (API failure)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONVENTIONAL_COMMIT_PATTERN = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)"
    r"(\(.+\))?!?: .+"
)


def get_repo_root() -> str:
    """Get the git repository root directory."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        print("Not in a git repository", file=sys.stderr)
        raise SystemExit(2)
    return result.stdout.strip()


def validate_conventional_commit(title: str) -> bool:
    """Validate title follows conventional commit format."""
    if not _CONVENTIONAL_COMMIT_PATTERN.match(title):
        print(
            "Title must follow conventional commit format: type(scope): description",
            file=sys.stderr,
        )
        valid = "feat, fix, docs, style, refactor, perf, test, chore, ci, build, revert"
        print(f"  Valid types: {valid}")
        print("  Example: feat: Add new feature")
        print("  Example: fix(auth): Resolve login issue")
        return False
    return True


def run_validations(repo_root: str, base: str, head: str) -> None:
    """Run pre-creation validations. Raises SystemExit(1) on failure."""
    os.makedirs(os.path.join(repo_root, ".agents"), exist_ok=True)

    print("Running validations...")
    print()

    # Validation 1: Session End (if .agents/ files changed)
    print("[1/3] Checking Session End protocol...")
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    changed_files = result.stdout.strip().splitlines() if result.returncode == 0 else []
    agents_changed = any(f.startswith(".agents/") for f in changed_files)

    if agents_changed:
        session_logs = [
            f for f in changed_files
            if re.match(r"^\.agents/sessions/.*\.md$", f)
        ]
        if session_logs:
            session_log = session_logs[-1]
            validate_script = os.path.join(repo_root, "scripts/Validate-Session.ps1")
            if os.path.exists(validate_script):
                session_log_path = os.path.join(repo_root, session_log)
                vresult = subprocess.run(
                    [
                        "pwsh", "-NoProfile", "-File",
                        validate_script,
                        "-SessionLogPath", session_log_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if vresult.returncode != 0:
                    print("Session End validation failed", file=sys.stderr)
                    raise SystemExit(1)
        else:
            print("  WARNING: No session log found but .agents/ files changed", file=sys.stderr)
    else:
        print("  No .agents/ changes, skipping")

    # Validation 2: Skill violation detection (WARNING)
    print()
    print("[2/3] Checking for skill violations...")
    skill_script = os.path.join(repo_root, "scripts/detect_skill_violation.py")
    if os.path.exists(skill_script):
        subprocess.run(
            [sys.executable, skill_script],
            timeout=30,
        )

    # Validation 3: Test coverage detection (WARNING)
    print()
    print("[3/3] Checking test coverage...")
    test_script = os.path.join(repo_root, "scripts/Detect-TestCoverageGaps.ps1")
    if os.path.exists(test_script):
        subprocess.run(
            ["pwsh", "-NoProfile", "-File", test_script],
            timeout=30,
        )

    print()
    print("All pre-creation validations passed!")
    print()


def write_audit_log(
    repo_root: str, head: str, base: str, title: str, reason: str,
) -> None:
    """Write audit log entry for skipped validation."""
    audit_dir = os.path.join(repo_root, ".agents/audit")
    os.makedirs(audit_dir, exist_ok=True)

    username = os.environ.get("USERNAME") or os.environ.get("USER", "unknown")

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    file_timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    audit_entry = (
        f"Timestamp: {timestamp}\n"
        f"Branch: {head} -> {base}\n"
        f"Title: {title}\n"
        f"User: {username}\n"
        f"Validation: SKIPPED\n"
        f"Reason: {reason}\n"
    )

    audit_file = os.path.join(audit_dir, f"pr-creation-skip-{file_timestamp}.txt")
    Path(audit_file).write_text(audit_entry, encoding="utf-8")
    print(f"Audit logged: {audit_file}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a GitHub PR with validation guardrails.",
    )
    parser.add_argument("--title", required=True, help="PR title in conventional commit format")
    parser.add_argument("--body", default="", help="PR description body")
    parser.add_argument("--body-file", default="", help="Path to file containing PR body")
    parser.add_argument("--base", default="main", help="Target branch (default: main)")
    parser.add_argument("--head", default="", help="Source branch (default: current branch)")
    parser.add_argument("--draft", action="store_true", help="Create as draft PR")
    parser.add_argument("--skip-validation", action="store_true", help="Skip validation checks")
    parser.add_argument(
        "--audit-reason", default="",
        help="Required when --skip-validation is used. Logged for audit trail.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = get_repo_root()

    # Require gh CLI
    gh_check = subprocess.run(
        ["gh", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if gh_check.returncode != 0:
        print("gh CLI not found. Install: https://cli.github.com/", file=sys.stderr)
        return 2

    # Get current branch if head not specified
    head = args.head
    if not head:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        head = result.stdout.strip()
        if not head:
            print("Could not determine current branch", file=sys.stderr)
            return 2

    # Validate conventional commit format
    if not validate_conventional_commit(args.title):
        return 2

    print(f"Preparing to create PR: {head} -> {args.base}")
    print(f"Title: {args.title}")
    print()

    # Handle validation skip with audit
    if args.skip_validation:
        if not args.audit_reason:
            print(
                "--skip-validation requires --audit-reason for audit trail",
                file=sys.stderr,
            )
            return 2
        print("WARNING: VALIDATION SKIPPED (audit logged)", file=sys.stderr)
        write_audit_log(repo_root, head, args.base, args.title, args.audit_reason)
        print()
    else:
        try:
            run_validations(repo_root, args.base, head)
        except SystemExit:
            raise
        except Exception as exc:
            print(f"Validation failed: {exc}", file=sys.stderr)
            return 1

    # Build gh pr create command
    gh_args = [
        "gh", "pr", "create",
        "--base", args.base,
        "--head", head,
        "--title", args.title,
    ]

    if args.body:
        gh_args.extend(["--body", args.body])
    elif args.body_file:
        if not os.path.exists(args.body_file):
            print(f"Body file not found: {args.body_file}", file=sys.stderr)
            return 2
        gh_args.extend(["--body-file", args.body_file])

    if args.draft:
        gh_args.append("--draft")

    # Create PR
    print("Creating PR...")
    result = subprocess.run(gh_args, text=True, timeout=60, check=False)
    exit_code = result.returncode

    if exit_code == 0:
        print()
        print("PR created successfully!")
        print()
        print("Next steps:")
        print("  - CI will run additional validations (PR description, QA, security)")
        print("  - Address any validation failures before merge")
        print("  - Wait for required approvals")
    else:
        print(f"PR creation failed (exit code: {exit_code})", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
