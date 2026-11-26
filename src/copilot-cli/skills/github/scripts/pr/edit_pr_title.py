#!/usr/bin/env python3
"""Edit a pull request title with a stale-write guard.

A squash merge uses the PR title as the commit subject, so fixing a title
before merge is a merge-message fix, not cosmetic work. Repositories whose
squash merge commit message is ``PR_TITLE`` (``manage_squash_merge_message.py``
reads that setting) make the title the whole commit subject line.

Safety behavior:
  - Reads the current title and refuses the write when ``--expected-title``
    is given and does not match, so a concurrent edit is not clobbered.
  - No-ops when the new title equals the current title.
  - Warns when the title does not parse as a conventional commit
    (``type(scope): description`` or ``type: description``), because the
    squash-merge subject stops validating.
  - Warns on em/en dashes, which bot reviewers flag.

Exit codes follow ADR-035:
    0 - Success (or no-op)
    1 - Logic or validation error, including a stale write
    2 - Usage, configuration, or not-found error
    3 - External service or API error
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from skill_bootstrap import ensure_plugin_paths

ensure_plugin_paths(__file__, (".claude", "lib"))

from github_core.api import (
    assert_gh_authenticated,
    resolve_repo_params,
)
from github_core.not_found import is_pr_not_found
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

_SCRIPT_NAME = "edit_pr_title.py"

# Prohibited characters as escapes: em dash (U+2014) and en dash (U+2013).
_DASH_RE = re.compile(r"[\u2013\u2014]")
_CONVENTIONAL_RE = re.compile(r"^[a-zA-Z]+(?:\([^)]*\))?!?: .+")

_TITLE_MAX = 256


def validate_title(title: str) -> list[str]:
    warnings: list[str] = []
    if _DASH_RE.search(title):
        warnings.append("Title contains an em/en dash; bot reviewers flag each occurrence")
    if not _CONVENTIONAL_RE.match(title):
        warnings.append(
            "Title does not parse as a conventional commit (type(scope): description); "
            "a squash merge uses the title as the commit subject"
        )
    if len(title) > _TITLE_MAX:
        warnings.append(f"Title is {len(title)} chars; GitHub truncates display past {_TITLE_MAX}")
    return warnings


def fetch_current_title(owner: str, repo: str, pr: int) -> str | None:
    result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/pulls/{pr}", "--jq", ".title"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        if is_pr_not_found(result.stderr):
            return None
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or f"gh api pulls/{pr} failed with no stderr or stdout output"
        )
    return result.stdout.rstrip("\n")


def update_title(owner: str, repo: str, pr: int, new_title: str) -> None:
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{owner}/{repo}/pulls/{pr}",
            "--method",
            "PATCH",
            "--input",
            "-",
        ],
        input=json.dumps({"title": new_title}),
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
            or f"gh api pulls/{pr} PATCH failed with no stderr or stdout output"
        )


_HELP_EPILOG = """\
examples:
  %(prog)s --pull-request 123 --title "fix(copilot-cli): map model tiers to the 5.5 ids"
  %(prog)s --pull-request 123 --title "..." --expected-title "old title" --dry-run

exit codes:
  0  success (or no-op)
  1  logic or validation error, including a stale write
  2  usage, configuration, or not-found error
  3  external service or API error
  4  auth error
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Edit a PR title with a stale-write guard.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--owner", default="")
    p.add_argument("--repo", default="")
    p.add_argument("--pull-request", type=int, required=True)
    p.add_argument("--title", required=True, help="New title text")
    p.add_argument(
        "--expected-title",
        default="",
        help="When provided and the current title differs, abort (exit 1) "
        "instead of clobbering a concurrent edit.",
    )
    p.add_argument("--dry-run", action="store_true")
    add_output_format_arg(p)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated(rest_only=True)
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    pr = args.pull_request

    new_title = args.title.strip()
    if not new_title:
        write_skill_error(
            "--title must not be blank",
            2,
            error_type="InvalidParams",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
        )
        return 2

    try:
        current_title = fetch_current_title(owner, repo, pr)
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        write_skill_error(
            str(exc), 3, error_type="ApiError", output_format=fmt, script_name=_SCRIPT_NAME
        )
        return 3

    if current_title is None:
        write_skill_error(
            f"PR #{pr} not found",
            2,
            error_type="NotFound",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
        )
        return 2

    if args.expected_title and args.expected_title != current_title:
        write_skill_error(
            f"PR #{pr} title changed since capture: expected "
            f"'{args.expected_title[:60]}' but current is '{current_title[:60]}'; "
            "concurrent edit detected, aborting",
            1,
            error_type="VerificationFailed",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
            extra={
                "pull_request": pr,
                "expected_title": args.expected_title,
                "current_title": current_title,
            },
        )
        return 1

    if new_title == current_title:
        write_skill_output(
            {
                "Success": True,
                "pull_request": pr,
                "action": "no-op",
                "title": current_title,
                "message": "Title unchanged; no write needed",
            },
            output_format=fmt,
            human_summary=f"PR #{pr}: title unchanged, no write",
            status="PASS",
            script_name=_SCRIPT_NAME,
        )
        return 0

    warnings = validate_title(new_title)

    if args.dry_run:
        write_skill_output(
            {
                "Success": True,
                "pull_request": pr,
                "action": "dry-run",
                "previous_title": current_title,
                "new_title": new_title,
                "warnings": warnings,
            },
            output_format=fmt,
            human_summary=f"PR #{pr}: dry-run (would set title)",
            status="PASS",
            script_name=_SCRIPT_NAME,
        )
        return 0

    try:
        update_title(owner, repo, pr, new_title)
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        write_skill_error(
            str(exc), 3, error_type="ApiError", output_format=fmt, script_name=_SCRIPT_NAME
        )
        return 3

    write_skill_output(
        {
            "Success": True,
            "pull_request": pr,
            "action": "updated",
            "previous_title": current_title,
            "new_title": new_title,
            "warnings": warnings,
        },
        output_format=fmt,
        human_summary=f"PR #{pr}: title updated ({len(warnings)} warning(s))",
        status="PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
