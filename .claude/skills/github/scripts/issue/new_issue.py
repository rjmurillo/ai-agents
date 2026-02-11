#!/usr/bin/env python3
"""Create a new GitHub Issue.

Supports both inline body text and file-based body content.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - File not found
    3 - External error (API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_WORKSPACE = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
    ),
)
sys.path.insert(0, _WORKSPACE)

from scripts.github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    resolve_repo_params,
)


def _write_github_output(outputs: dict[str, str]) -> None:
    """Write key=value pairs to GITHUB_OUTPUT if available."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    try:
        with open(output_file, "a", encoding="utf-8") as fh:
            for key, value in outputs.items():
                fh.write(f"{key}={value}\n")
    except OSError:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a new GitHub Issue.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--title", required=True, help="Issue title")

    body_group = parser.add_mutually_exclusive_group()
    body_group.add_argument("--body", default="", help="Issue body text")
    body_group.add_argument("--body-file", default="", help="Path to file containing issue body")

    parser.add_argument(
        "--labels",
        default="",
        help='Comma-separated list of labels (e.g., "bug,P1,needs-triage")',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["Owner"], resolved["Repo"]

    if not args.title or not args.title.strip():
        error_and_exit("Title cannot be empty.", 1)

    body = args.body
    if args.body_file:
        body_path = Path(args.body_file)
        if not body_path.exists():
            error_and_exit(f"Body file not found: {args.body_file}", 2)
        body = body_path.read_text(encoding="utf-8")

    gh_args = ["gh", "issue", "create", "--repo", f"{owner}/{repo}", "--title", args.title]

    if body and body.strip():
        gh_args.extend(["--body", body])

    if args.labels and args.labels.strip():
        gh_args.extend(["--label", args.labels])

    result = subprocess.run(gh_args, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        error_and_exit(f"Failed to create issue: {error_str}", 3)

    output_text = result.stdout.strip()
    match = re.search(r"issues/(\d+)", output_text)
    if not match:
        error_and_exit(f"Could not parse issue number from result: {output_text}", 3)

    issue_number = int(match.group(1))

    output = {
        "success": True,
        "issue_number": issue_number,
        "url": output_text,
        "title": args.title,
    }
    print(json.dumps(output, indent=2))

    _write_github_output({
        "success": "true",
        "issue_number": str(issue_number),
        "issue_url": output_text,
    })

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
