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
import importlib.util
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_sibling(name: str):
    """Load a sibling script by ABSOLUTE PATH, without touching ``sys.path``.

    ``new_pr.py`` runs under ``python3 -I`` (the push-pr identity guard
    requires that exact form), and isolated mode removes the script's own
    directory from ``sys.path``. Measured on CPython 3.14.6:

        $ python3 -I main.py
        ModuleNotFoundError: No module named 'sibling'

    So a plain ``import pr_validations`` cannot resolve here. Loading the file
    directly keeps the isolation ``-I`` exists to provide. The rejected
    alternative, ``sys.path.insert(0, os.path.dirname(__file__))``, would let
    anyone able to write into the script directory shadow a stdlib module for
    this process, which is strictly worse than the position before the split.

    The identity guard pins the SHA-256 of every file in this bundle, so a
    sibling cannot be swapped independently of new_pr.py.
    """
    path = Path(__file__).resolve().with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load required sibling module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_validations = _load_sibling("pr_validations")

# Re-exported so `new_pr.<name>` stays the import surface for callers and
# tests. The split is an internal reorganization, not an interface change.
run_validations = _validations.run_validations
validate_no_escaped_newlines = _validations.validate_no_escaped_newlines
_extract_validatable_session_logs = _validations._extract_validatable_session_logs
_report_not_run = _validations._report_not_run
_WarningLog = _validations._WarningLog
_DASH_RE = _validations._DASH_RE
_SKILL_SCAN_EXTENSIONS = _validations._SKILL_SCAN_EXTENSIONS
_SESSION_LOG_FILENAME_RE = _validations._SESSION_LOG_FILENAME_RE
_UNTRUSTED_REPOSITORY_VALIDATORS = _validations._UNTRUSTED_REPOSITORY_VALIDATORS
_UNTRUSTED_REPOSITORY_REASON = _validations._UNTRUSTED_REPOSITORY_REASON
_git_env = _validations._git_env

# Python 3.10 compatibility (issue #4764). `datetime.UTC` is an alias for
# `datetime.timezone.utc` that CPython added in 3.11, so
# `from datetime import UTC` raises ImportError on 3.10:
#
#     ImportError: cannot import name 'UTC' from 'datetime'
#
# Measured on CPython 3.10.20 against this file at commit 5cd72a7dad. This
# script runs on the HOST's ambient interpreter, not the repository's 3.14
# development interpreter, and `.claude/rules/python.md` puts the
# hook-portability floor at 3.10. `timezone.utc` is the same object and exists
# at every version this repository targets, so it is the portable spelling
# rather than a compatibility shim.
#
# The repository development floor is unchanged: pyproject.toml still declares
# `requires-python = ">=3.14"`. Only host-executed scripts write to 3.10.
_UTC = timezone.utc

_CONVENTIONAL_COMMIT_PATTERN = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)"
    r"(\(.+\))?!?: .+"
)


def _resolve_validation_base(pr_base: str, explicit: str = "") -> str:
    """Return the git ref to use for local validation diffs.

    The ``--base`` value (e.g. ``main``) names a branch on GitHub. In a linked
    worktree the local ref of that name is never advanced after the worktree is
    created, so ``git diff main...HEAD`` diffs against a merge-base that may be
    hundreds of commits stale and includes unrelated files (issues #4461, #4489).

    Resolution priority:
    1. ``explicit`` -- when the caller passes ``--validation-base``, trust it.
    2. ``origin/{pr_base}`` -- when the remote-tracking ref exists, use it.
       This ref is kept current by normal ``git fetch`` without checking out
       ``{pr_base}`` locally, so it is always correct in a worktree.
    3. ``pr_base`` fallback -- non-remote repos or unusual layouts where no
       ``origin/`` remote exists.

    The returned ref is used ONLY for ``git diff``; ``gh pr create --base``
    always receives the bare ``pr_base`` name, which is what GitHub expects.
    """
    if explicit:
        return explicit

    remote_ref = f"origin/{pr_base}"
    result = subprocess.run(
        ["git", "rev-parse", "--verify", remote_ref],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        env=_git_env(),
    )
    if result.returncode == 0:
        return remote_ref
    return pr_base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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

    timestamp = datetime.now(_UTC).strftime("%Y-%m-%d %H:%M:%S")
    file_timestamp = datetime.now(_UTC).strftime("%Y%m%d-%H%M%S")

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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = get_repo_root()

    # Require gh CLI
    gh_check = subprocess.run(
        ["gh", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
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
            encoding="utf-8",
            errors="replace",
            timeout=10,
            env=_git_env(),
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
                body=args.body,
                body_file=args.body_file,
            )
        except SystemExit:
            raise
        except Exception as exc:
            print(f"Validation failed: {exc}", file=sys.stderr)
            return 1

    # Build gh pr create command
    gh_args = [
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
    sys.stdout.flush()
    result = subprocess.run(
        gh_args, text=True, encoding="utf-8", errors="replace", timeout=60, check=False
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


if __name__ == "__main__":
    raise SystemExit(main())
