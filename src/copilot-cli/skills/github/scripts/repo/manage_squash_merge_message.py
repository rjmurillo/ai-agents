#!/usr/bin/env python3
"""Read or update the repository's squash-merge commit message source.

Wraps the GitHub REST `repos/{owner}/{repo}` field
`squash_merge_commit_message`, whose allowed values are `PR_BODY`,
`COMMIT_MESSAGES`, `PR_BODY_AND_COMMIT_DETAILS`, and `BLANK` (confirmed live
via `gh api repos/{owner}/{repo} --jq .squash_merge_commit_message` during
Issue #4462 triage, alongside the sibling `squash_merge_commit_title` field,
which this script does not touch).

Issue #4462: a repository left on `COMMIT_MESSAGES` folds every commit
message into the squash commit, so a closing keyword left in an intermediate
commit (never reviewed as part of the PR description) can close an issue on
merge. `audit_closing_claims.py` (same skill, `scripts/pr/`) detects that
condition across open PRs; this script is the guarded way to change the
setting that controls it, so the change is deliberate and auditable rather
than a manual `gh api --method PATCH` with no before/after record.

Guard behaviour:
  - `--expected-current` aborts (exit 1) if the live value does not match,
    so a caller cannot overwrite a setting someone else already changed
    between the caller's read and this write (the same stale-write shape
    `edit_pr_body.py`'s `--expected-hash` guards for PR bodies).
  - No write happens when the requested value already matches the live
    value; the run is reported as a no-op, not an error.
  - `--dry-run` reports what would change without writing.
  - After a real write, the setting is read back and reported as `after`,
    rather than assumed from the requested value, so the report reflects
    what GitHub actually persisted.

Exit codes follow ADR-035:
    0 - Success (read, no-op, dry-run, or applied write)
    1 - Guard failure: --expected-current did not match the live value
    2 - Usage or configuration error
    3 - External service or API error
    4 - Auth error
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

_SCRIPT_NAME = "manage_squash_merge_message.py"

# GitHub REST's allowed values for repos/{owner}/{repo}.squash_merge_commit_message.
_ALLOWED_VALUES = ("PR_BODY", "COMMIT_MESSAGES", "PR_BODY_AND_COMMIT_DETAILS", "BLANK")


def fetch_current_setting(owner: str, repo: str) -> str:
    """Return the live `squash_merge_commit_message` value."""
    result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}", "--jq", ".squash_merge_commit_message"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or f"gh api repos/{owner}/{repo} failed with no stderr or stdout output"
        )
    return result.stdout.strip() or "PR_BODY"


def update_setting(owner: str, repo: str, new_value: str) -> None:
    """Write `squash_merge_commit_message` via the gh CLI."""
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}",
            "--method", "PATCH",
            "--field", f"squash_merge_commit_message={new_value}",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or f"gh api repos/{owner}/{repo} PATCH failed with no stderr or stdout output"
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Read or update squash_merge_commit_message with a stale-write guard.",
    )
    p.add_argument("--owner", default="")
    p.add_argument("--repo", default="")
    p.add_argument(
        "--set", choices=_ALLOWED_VALUES, default=None,
        help="New squash_merge_commit_message value. Omit to read-only.",
    )
    p.add_argument(
        "--expected-current", choices=_ALLOWED_VALUES, default=None,
        help=(
            "Abort (exit 1) if the live value does not match this. Guards "
            "against overwriting a setting someone else already changed."
        ),
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Report what would change without writing.",
    )
    add_output_format_arg(p)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    try:
        current = fetch_current_setting(owner, repo)
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        write_skill_error(
            str(exc), 3, error_type="ApiError",
            output_format=fmt, script_name=_SCRIPT_NAME,
        )
        return 3

    if args.expected_current and args.expected_current != current:
        write_skill_error(
            f"squash_merge_commit_message is {current!r}, expected {args.expected_current!r}; "
            "aborting to avoid overwriting a concurrent change",
            1,
            error_type="VerificationFailed",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
            extra={"owner": owner, "repo": repo, "before": current},
        )
        return 1

    if args.set is None:
        write_skill_output(
            {"Success": True, "owner": owner, "repo": repo,
             "action": "read", "before": current, "after": current},
            output_format=fmt,
            human_summary=f"{owner}/{repo}: squash_merge_commit_message is {current}",
            status="PASS",
            script_name=_SCRIPT_NAME,
        )
        return 0

    if args.set == current:
        write_skill_output(
            {"Success": True, "owner": owner, "repo": repo,
             "action": "no-op", "before": current, "after": current},
            output_format=fmt,
            human_summary=f"{owner}/{repo}: already {current}, no write needed",
            status="PASS",
            script_name=_SCRIPT_NAME,
        )
        return 0

    if args.dry_run:
        write_skill_output(
            {"Success": True, "owner": owner, "repo": repo,
             "action": "dry-run", "before": current, "would_set": args.set},
            output_format=fmt,
            human_summary=f"{owner}/{repo}: dry-run, would set {current} -> {args.set}",
            status="PASS",
            script_name=_SCRIPT_NAME,
        )
        return 0

    try:
        update_setting(owner, repo, args.set)
        after = fetch_current_setting(owner, repo)
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        write_skill_error(
            str(exc), 3, error_type="ApiError",
            output_format=fmt, script_name=_SCRIPT_NAME,
        )
        return 3

    write_skill_output(
        {"Success": True, "owner": owner, "repo": repo,
         "action": "updated", "before": current, "after": after},
        output_format=fmt,
        human_summary=f"{owner}/{repo}: squash_merge_commit_message {current} -> {after}",
        status="PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
