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

_CONVENTIONAL_COMMIT_PATTERN = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)"
    r"(\(.+\))?!?: .+"
)


def validate_no_escaped_newlines(body_content: str) -> None:
    """Reject a body made from literal backslash-n sequences."""
    escaped_count = body_content.count("\\n")
    if not escaped_count or "\n" in body_content.strip():
        return
    print(
        f"ERROR: Body carries {escaped_count} literal backslash-n"
        " sequence(s) and no line break, so GitHub would render it as one"
        " unbroken paragraph and drop every heading, list and table.",
        file=sys.stderr,
    )
    print(
        "  Write the body to a file and pass --body-file, which cannot"
        " express this error.",
        file=sys.stderr,
    )
    raise SystemExit(1)

# Em/en-dash detection regex for Validation 5. Inlined here rather than
# imported from scripts.validation.pr_description because:
#
# 1. This file is one of two copies the project keeps in sync:
#    - .claude/skills/github/scripts/pr/new_pr.py (the source the
#      developer edits)
#    - src/copilot-cli/skills/github/scripts/pr/new_pr.py (the
#      generated copy produced by build/scripts/build_all.py)
#    Both copies live at different depths from the repo root
#    (parents[5] vs parents[6]), so any cross-package import requires
#    path resolution that works at both depths. The complexity (walking
#    up looking for a marker, subprocess git calls, etc.) is not worth
#    it for a 5-line regex.
# 2. The detection logic is small (compile, search). Drift between the
#    two definitions (this one and scripts.validation.pr_description's
#    _DASH_RE) is caught by the test suite (tests/test_new_pr.py and
#    tests/test_validation_pr_description.py) which exercises both with
#    the same fixtures.
# 3. The two layers serve different purposes: this is the pre-creation
#    guard, scripts.validation.pr_description is the CI fallback. Keeping
#    them independent lets each fail open or fail closed differently per
#    its threat model.
#
# Uses Unicode escape sequences so this source file does not contain
# U+2014 or U+2013 itself per `.claude/rules/universal.md` MUST NOT
# entry 5 (Issue #1923).
_DASH_RE = re.compile("[\u2013\u2014]")

# Extensions the skill-violation scanner (scripts/detect_skill_violation.py)
# actually inspects. Filtering changed files to this set before building the
# scan argv keeps the command line short on large diffs and skips the
# subprocess entirely when no changed file is scannable. This mirrors
# detect_skill_violation.VALID_EXTENSIONS; the two are kept in sync by
# test_new_pr.py, which imports both and asserts equality (same drift-guard
# strategy as _DASH_RE above). A local constant avoids the cross-package
# import path resolution the _DASH_RE comment documents rejecting.
_SKILL_SCAN_EXTENSIONS = frozenset({".md", ".py", ".ps1", ".psm1"})


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


def _resolve_validation_head(head: str) -> str:
    """Return the commit used for validations, falling back to ``head``."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{head}^{{commit}}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        env=_git_env(),
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return head


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_env() -> dict[str, str]:
    """Return environment with git hook override variables stripped."""
    return {
        k: v
        for k, v in os.environ.items()
        if k not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"}
    }


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


_SESSION_LOG_FILENAME_RE = re.compile(
    # Canonical filename per session-init script:
    # .agents/sessions/YYYY-MM-DD-session-NN[-keyword1-keyword2-...].{md|json}
    # Keywords are kebab-case (lowercase letters/digits + hyphens only).
    r"^\.agents/sessions/"
    r"\d{4}-\d{2}-\d{2}-session-\d+"
    r"(?:-[a-z0-9-]+)?"
    r"\.(md|json)$"
)


def _extract_validatable_session_logs(
    changed_files: list[str],
) -> tuple[list[str], bool]:
    """Return (JSON session logs, legacy_md_present) from changed files.

    Filename pattern requires YYYY-MM-DD-session-NN prefix to exclude
    tally files like STEP-0-METRICS.md and STEP-0.5-METRICS.md.
    validate_session_json.py only accepts JSON. Legacy .md session logs
    require migration (handled by the CI workflow at
    .github/workflows/ai-session-protocol.yml). Local pre-PR validation
    only checks JSON; warn the author so they know CI will migrate.

    Returns a tuple so callers can distinguish "no session log at all"
    (both empty) from "legacy .md staged, no JSON to validate locally"
    (validatable empty, has_legacy_md True).
    """
    matched = [f for f in changed_files if _SESSION_LOG_FILENAME_RE.match(f)]
    legacy_md = [f for f in matched if f.endswith(".md")]
    if legacy_md:
        print(
            f"  WARNING: legacy .md session log(s) staged ({legacy_md}); "
            "CI workflow will migrate to JSON before validation. Local "
            "pre-PR validation only runs against JSON session logs.",
            file=sys.stderr,
        )
    return [f for f in matched if f.endswith(".json")], bool(legacy_md)


# Issue #4764: /push-pr must not execute repository-controlled Python to decide
# whether to create a pull request. All three detectors named below live under
# scripts/, which any branch can rewrite, so this script never runs them and
# reports them as not run. CI runs them from a trusted checkout.
#
# Issue #4825 review 4894113215 finding 1: this was previously a helper that
# ignored all three of its arguments and always returned False. It printed
# "Skipped ... because scripts/ is changed or dirty" on a clean branch, did not
# record the skip, and still summarized the run as "All pre-creation
# validations passed!". The boundary is a constant policy, not a runtime
# condition, so it is spelled as one.
_UNTRUSTED_REPOSITORY_VALIDATORS = (
    "Session End (scripts/validate_session_json.py)",
    "skill violation (scripts/detect_skill_violation.py)",
    "test coverage (scripts/detect_test_coverage_gaps.py)",
)
_UNTRUSTED_REPOSITORY_REASON = (
    "repository-local Python is outside the trusted push-pr boundary"
)

def _report_not_run(validator: str) -> None:
    """Name a validator this script deliberately does not run."""
    print(f"  Not run: {validator}.")
    print(f"  Reason: {_UNTRUSTED_REPOSITORY_REASON}; CI runs it from a trusted checkout.")


def run_validations(
    repo_root: str,
    base: str,
    head: str,
    *,
    title: str = "",
    body: str = "",
    body_file: str = "",
) -> None:
    """Run pre-creation validations. Raises SystemExit(1) on failure."""
    try:
        os.makedirs(os.path.join(repo_root, ".agents"), exist_ok=True)
    except PermissionError as exc:
        print(f"Warning: Could not create .agents directory: {exc}", file=sys.stderr)

    print("Running validations...")
    print()

    # Validation 1: Session End (if .agents/ files changed)
    print("[1/6] Checking Session End protocol...")
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=_git_env(),
    )
    diff_failed = result.returncode != 0
    if diff_failed:
        print(
            f"  WARNING: 'git diff {base}...{head}' failed (exit {result.returncode}); "
            "the changed-file set is unknown. Validations that rely on it are "
            "skipped, not treated as 'no changes'.",
            file=sys.stderr,
        )
    changed_files = result.stdout.strip().splitlines() if not diff_failed else []
    agents_changed = any(f.startswith(".agents/") for f in changed_files)

    if agents_changed:
        session_logs, has_legacy_md = _extract_validatable_session_logs(
            changed_files
        )
        if session_logs:
            _report_not_run(_UNTRUSTED_REPOSITORY_VALIDATORS[0])
        elif not has_legacy_md:
            print("  WARNING: No session log found but .agents/ files changed", file=sys.stderr)
    elif diff_failed:
        print("  Skipped: git diff failed, changed files unknown (see warning above).")
    else:
        print("  No .agents/ changes, skipping")

    # Validation 2: Skill violation detection (WARNING)
    print()
    print("[2/6] Checking for skill violations...")
    scannable_files = [f for f in changed_files if Path(f).suffix in _SKILL_SCAN_EXTENSIONS]
    _report_not_run(_UNTRUSTED_REPOSITORY_VALIDATORS[1])
    if diff_failed:
        print("  Scope: unknown, git diff failed (see warning above).")
    elif not changed_files:
        print("  Scope: no changed files.")
    elif not scannable_files:
        _exts = ", ".join(sorted(_SKILL_SCAN_EXTENSIONS))
        print(f"  Scope: no changed file has a scannable extension ({_exts}).")
    else:
        print(f"  Scope: {len(scannable_files)} changed file(s) would have been scanned.")

    # Validation 3: Test coverage detection (WARNING)
    print()
    print("[3/6] Checking test coverage...")
    _report_not_run(_UNTRUSTED_REPOSITORY_VALIDATORS[2])

    # Validation 4: PR Description validation (WARNING)
    print()
    print("[4/6] Validating PR description...")
    validate_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "validate_pr_description.py",
    )
    if os.path.exists(validate_script) and title:
        val_args = [sys.executable, "-I", validate_script, "--title", title]
        if body:
            val_args.extend(["--body", body])
        elif body_file:
            val_args.extend(["--body-file", body_file])
        val_result = subprocess.run(
            val_args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        # Print human-readable output (on stderr from validator)
        if val_result.stderr:
            print(val_result.stderr, end="", file=sys.stderr)
        # Warning mode: don't fail on exit code
    else:
        print("  Skipped (no title available or validator not found)")

    # Validation 5: Em/en-dash check (CRITICAL, blocks creation)
    # PR descriptions live in GitHub and never reach Git hook stdin, so the
    # Lefthook jobs declared in lefthook.yml cannot scan them.
    # This is the shift-left guard that prevents dashes from being submitted
    # at all. Closes the gap that allowed PR #1930 to ship with em/en-dashes
    # in the description despite local dash checks.
    # Rule: .claude/rules/universal.md MUST NOT entry 5. Refs Issue #1923.
    print()
    print("[5/6] Em/en-dash check on title and body...")
    body_content = body or ""
    if not body_content and body_file and os.path.exists(body_file):
        try:
            with open(body_file, encoding="utf-8") as f:
                body_content = f.read()
        except OSError as exc:
            print(f"  WARNING: Could not read body file: {exc}", file=sys.stderr)
    dash_violations: list[str] = []
    if _DASH_RE.search(title):
        dash_violations.append("title")
    body_dash_lines = [
        f"line {n}"
        for n, line in enumerate(body_content.splitlines(), start=1)
        if _DASH_RE.search(line)
    ]
    if body_dash_lines:
        sample = ", ".join(body_dash_lines[:5])
        if len(body_dash_lines) > 5:
            sample += f", ... (+{len(body_dash_lines) - 5} more)"
        dash_violations.append(f"body ({sample})")
    if dash_violations:
        print(
            "ERROR: Em-dash (U+2014) or en-dash (U+2013) found in: "
            + "; ".join(dash_violations),
            file=sys.stderr,
        )
        print(
            "  Replace with comma, period, hyphen, or restructure.",
            file=sys.stderr,
        )
        print(
            "  Rule: .claude/rules/universal.md MUST NOT entry 5 (Issue #1923).",
            file=sys.stderr,
        )
        print(
            "  Override (NOT RECOMMENDED): re-run with --skip-validation"
            " --audit-reason \"...\".",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print("  No prohibited characters in title or body.")

    print()
    print("[6/6] Escaped-newline check on body...")
    validate_no_escaped_newlines(body_content)
    print("  Body line breaks are real newlines.")

    print()
    print(
        "Trusted pre-creation validations passed. "
        f"{len(_UNTRUSTED_REPOSITORY_VALIDATORS)} repository-local check(s) did "
        "not run: " + ", ".join(_UNTRUSTED_REPOSITORY_VALIDATORS) + "."
    )
    print(f"  Reason: {_UNTRUSTED_REPOSITORY_REASON}.")
    print()


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
        validation_head = _resolve_validation_head(head)
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
                validation_head,
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
