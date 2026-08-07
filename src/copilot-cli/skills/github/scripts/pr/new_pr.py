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
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from new_pr_validations import (
    _SKILL_SCAN_EXTENSIONS as _VALIDATION_SKILL_SCAN_EXTENSIONS,
)
from new_pr_validations import (
    _git_env,
    _resolve_validation_base,
    run_validations,
)
from prepare_pr_body import (
    PreparePrBodyError,
    prepare_pr_body,
    read_prepared_pr_body,
)
from validate_pr_description import _CONVENTIONAL_COMMIT_PATTERN

_SKILL_SCAN_EXTENSIONS = _VALIDATION_SKILL_SCAN_EXTENSIONS


def get_repo_root() -> str:
    """Get the current worktree root directory.

    Uses --show-toplevel, not --git-common-dir. In a LINKED worktree the
    common dir is the MAIN checkout's shared .git, so dirname(common-dir)
    is the main checkout, not this worktree (#2387). --show-toplevel returns
    the current worktree root in every layout. Canonical reference:
    scripts/github_core/repo.py::get_repo_root.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        env=_git_env(),
    )
    if result.returncode != 0 or not result.stdout.strip():
        print("Not in a git repository", file=sys.stderr)
        raise SystemExit(2)
    toplevel = Path(result.stdout.strip())
    if not toplevel.is_absolute():
        toplevel = (Path.cwd() / toplevel).resolve()
    else:
        toplevel = toplevel.resolve()
    return str(toplevel)


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


def write_audit_log(
    repo_root: str,
    head: str,
    base: str,
    title: str,
    reason: str,
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
    parser.add_argument("--title", default="", help="PR title in conventional commit format")
    parser.add_argument("--body", default="", help="PR description body")
    parser.add_argument("--body-file", default="", help="Path to file containing PR body")
    parser.add_argument(
        "--prepare-body-file",
        action="store_true",
        help="Create a private .agents/scratch/pr-body-*.md path and exit",
    )
    parser.add_argument("--base", default="main", help="Target branch (default: main)")
    parser.add_argument(
        "--validation-base",
        default="",
        dest="validation_base",
        help=(
            "Git ref for local validation diffs (default: auto-resolved to "
            "origin/<base> when that ref exists, else <base>). Use this to "
            "override the automatic resolution. Does not affect the GitHub "
            "PR base branch."
        ),
    )
    parser.add_argument("--head", default="", help="Source branch (default: current branch)")
    parser.add_argument("--draft", action="store_true", help="Create as draft PR")
    parser.add_argument("--skip-validation", action="store_true", help="Skip validation checks")
    parser.add_argument(
        "--audit-reason",
        default="",
        help="Required when --skip-validation is used. Logged for audit trail.",
    )
    return parser


def _prepare_body_file(repo_root: str) -> int:
    """Create a secure prepared-body path and print it."""
    try:
        print(prepare_pr_body(Path(repo_root)).as_posix())
    except (OSError, PreparePrBodyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


def _read_body(args: argparse.Namespace, repo_root: str) -> str | None:
    """Validate body arguments and securely read a prepared body file."""
    if not args.title:
        print("--title is required", file=sys.stderr)
        return None
    if args.body and args.body_file:
        print("--body and --body-file are mutually exclusive", file=sys.stderr)
        return None

    body = args.body
    if args.body_file:
        try:
            body = read_prepared_pr_body(Path(repo_root), args.body_file)
        except (OSError, UnicodeError, PreparePrBodyError) as exc:
            print(f"Invalid body file: {exc}", file=sys.stderr)
            return None
    return body


def _gh_is_available() -> bool:
    """Return whether the GitHub CLI can be executed."""
    result = subprocess.run(
        ["gh", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if result.returncode != 0:
        print("gh CLI not found. Install: https://cli.github.com/", file=sys.stderr)
        return False
    return True


def _resolve_head(explicit_head: str) -> str | None:
    """Return the requested head or the current branch."""
    if explicit_head:
        return explicit_head
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        env=_git_env(),
    )
    head = result.stdout.strip()
    if not head:
        print("Could not determine current branch", file=sys.stderr)
        return None
    return head


def _run_pre_creation_validations(
    args: argparse.Namespace,
    repo_root: str,
    head: str,
    body: str,
) -> int | None:
    """Validate the request or write the audited validation skip."""
    if not validate_conventional_commit(args.title):
        return 2

    print(f"Preparing to create PR: {head} -> {args.base}")
    print(f"Title: {args.title}")
    print()

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
        return None

    validation_base = _resolve_validation_base(args.base, args.validation_base)
    if validation_base != args.base:
        print(
            f"  Note: validating diff against {validation_base!r} "
            f"(local {args.base!r} may be stale in a worktree). "
            f"GitHub PR base remains {args.base!r}.",
            file=sys.stderr,
        )
    try:
        run_validations(
            repo_root,
            validation_base,
            head,
            title=args.title,
            body=body,
            body_file="",
        )
    except Exception as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1
    return None


def _build_gh_args(
    args: argparse.Namespace,
    head: str,
    body: str,
) -> list[str]:
    """Build the ``gh pr create`` command."""
    arguments = [
        "gh",
        "pr",
        "create",
        "--base",
        args.base,
        "--head",
        head,
        "--title",
        args.title,
    ]
    if body or args.body_file:
        arguments.extend(["--body-file", "-"])
    if args.draft:
        arguments.append("--draft")
    return arguments


def _create_pr(args: argparse.Namespace, head: str, body: str) -> int:
    """Create the pull request and report the result."""
    print("Creating PR...")
    sys.stdout.flush()
    result = subprocess.run(
        _build_gh_args(args, head, body),
        input=body if body or args.body_file else None,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = get_repo_root()

    if args.prepare_body_file:
        return _prepare_body_file(repo_root)

    body = _read_body(args, repo_root)
    if body is None:
        return 2

    if not _gh_is_available():
        return 2

    head = _resolve_head(args.head)
    if head is None:
        return 2

    validation_exit = _run_pre_creation_validations(args, repo_root, head, body)
    if validation_exit is not None:
        return validation_exit

    return _create_pr(args, head, body)


if __name__ == "__main__":
    raise SystemExit(main())
