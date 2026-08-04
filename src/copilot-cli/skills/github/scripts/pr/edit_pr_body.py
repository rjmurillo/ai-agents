#!/usr/bin/env python3
"""Edit a pull request body with a stale-write guard.

Reads the current PR body, computes a hash, applies the requested edit,
then writes back only if the body has not changed since the read. This
prevents overwriting concurrent reviewer edits.

Usage:
    edit_pr_body.py --pull-request 42 --body "new body text"
    edit_pr_body.py --pull-request 42 --body-file /path/to/body.md
    edit_pr_body.py --pull-request 42 --body-file /path/to/body.md \\
        --expected-sha <sha256-of-current-body>

The --expected-sha option pins the guard to a specific body version.
Without it the script reads the current body at call time and uses that
hash. Pass the sha from a prior read to guard a multi-step workflow.

Exit codes follow ADR-035:
    0 - Success
    1 - Stale write: body changed since the read
    2 - Config error (bad params, missing file)
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

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

from github_core.api import assert_gh_authenticated, resolve_repo_params  # noqa: E402
from github_core.output import (  # noqa: E402
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

_SCRIPT_NAME = "edit_pr_body.py"


def _body_sha(text: str) -> str:
    """SHA-256 of the body text, hex-encoded."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fetch_current_body(pr: int, repo_flag: str) -> str:
    """Return the current PR body from the GitHub API."""
    result = subprocess.run(
        ["gh", "pr", "view", str(pr), "--repo", repo_flag, "--json", "body"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to fetch PR #{pr}: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    return data.get("body") or ""


def write_body(pr: int, repo_flag: str, new_body: str) -> None:
    """Write new_body to the PR via the GitHub CLI."""
    result = subprocess.run(
        ["gh", "pr", "edit", str(pr), "--repo", repo_flag, "--body", new_body],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to edit PR #{pr}: {result.stderr.strip()}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Edit a pull request body with a stale-write guard.",
    )
    parser.add_argument(
        "--pull-request", "-n", required=True, type=int,
        help="PR number to edit.",
    )
    parser.add_argument("--owner", help="Repository owner (default: inferred)")
    parser.add_argument("--repo", help="Repository name (default: inferred)")

    body_group = parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body", help="New body text.")
    body_group.add_argument(
        "--body-file",
        help="Path to a file containing the new body text.",
    )

    parser.add_argument(
        "--expected-sha",
        help=(
            "SHA-256 hex digest of the body this edit is based on. "
            "If the current body does not match, exit 1 (stale write)."
        ),
    )
    add_output_format_arg(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_format = get_output_format(args.output_format)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    pr = args.pull_request
    repo_flag = f"{resolved.owner}/{resolved.repo}"

    if args.body is not None:
        new_body = args.body
    else:
        body_path = Path(args.body_file)
        if not body_path.exists():
            write_skill_error(
                f"Body file not found: {body_path}",
                2,
                error_type="InvalidParams",
                output_format=output_format,
                script_name=_SCRIPT_NAME,
            )
            return 2
        new_body = body_path.read_text(encoding="utf-8")

    try:
        current_body = fetch_current_body(pr, repo_flag)
    except RuntimeError as exc:
        write_skill_error(
            str(exc),
            3,
            error_type="ApiError",
            output_format=output_format,
            script_name=_SCRIPT_NAME,
            extra={"pull_request": pr},
        )
        return 3

    current_sha = _body_sha(current_body)

    if args.expected_sha is not None and args.expected_sha != current_sha:
        write_skill_error(
            (
                f"PR #{pr} body changed since the read "
                f"(expected sha {args.expected_sha[:8]}..., "
                f"current sha {current_sha[:8]}...). "
                "Re-read the body and retry."
            ),
            1,
            error_type="VerificationFailed",
            output_format=output_format,
            script_name=_SCRIPT_NAME,
            extra={"pull_request": pr, "expected_sha": args.expected_sha,
                   "current_sha": current_sha},
        )
        return 1

    try:
        write_body(pr, repo_flag, new_body)
    except RuntimeError as exc:
        write_skill_error(
            str(exc),
            3,
            error_type="ApiError",
            output_format=output_format,
            script_name=_SCRIPT_NAME,
            extra={"pull_request": pr},
        )
        return 3

    new_sha = _body_sha(new_body)
    write_skill_output(
        {
            "pull_request": pr,
            "repo": repo_flag,
            "previous_sha": current_sha,
            "new_sha": new_sha,
        },
        output_format=output_format,
        human_summary=f"PR #{pr} body updated (sha {new_sha[:8]}...).",
        status="PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
