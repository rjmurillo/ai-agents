#!/usr/bin/env python3
"""Check whether an open PR already addresses a given issue (issue #2477).

Pre-flight guard against competing PRs: before an autonomous pipeline or an
interactive session opens a new PR for an issue, it should confirm no open PR
already claims that issue via a closing keyword. Two workers acting on the same
issue otherwise open duplicate PRs (the #2477 failure mode).

Detection is deterministic: list open PRs and match each body/title against the
GitHub closing-keyword forms for the issue number (Fixes/Closes/Resolves and the
non-closing Refs), rather than a fragile free-text search.

Exit codes follow ADR-035:
    0 - No open PR references the issue (safe to proceed)
    1 - One or more open PRs already reference the issue (do not open a duplicate)
    3 - External error (gh/API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    resolve_repo_params,
)
from github_core.output import (  # noqa: E402
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

# GitHub closing keywords plus the non-closing "Refs"/"Ref". Matched against an
# issue number, case-insensitively, requiring the "#" form so a bare number in
# prose does not produce a false positive.
_KEYWORDS = "close[sd]?|fix(e[sd])?|resolve[sd]?|ref[s]?"


def references_issue(text: str, issue: int) -> bool:
    """Return True if ``text`` links to ``issue`` via a closing/refs keyword."""

    if not text:
        return False
    pattern = re.compile(rf"(?i)\b(?:{_KEYWORDS})\b[\s:]*#{issue}\b")
    return bool(pattern.search(text))


def find_open_prs_for_issue(owner: str, repo: str, issue: int) -> list[dict]:
    """Return open PRs whose title or body references ``issue``."""

    result = subprocess.run(
        ["gh", "pr", "list", "--repo", f"{owner}/{repo}", "--state", "open",
         "--limit", "200", "--json", "number,title,body,url,headRefName"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh pr list failed")
    try:
        prs = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as err:
        raise RuntimeError("could not parse gh pr list output") from err
    matches = []
    for pr in prs if isinstance(prs, list) else []:
        text = f"{pr.get('title', '')}\n{pr.get('body', '') or ''}"
        if references_issue(text, issue):
            matches.append({
                "number": pr.get("number"),
                "title": pr.get("title", ""),
                "url": pr.get("url", ""),
                "head": pr.get("headRefName", ""),
            })
    return matches


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check whether an open PR already addresses an issue.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    add_output_format_arg(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    fmt = get_output_format(args.output_format)

    try:
        matches = find_open_prs_for_issue(owner, repo, args.issue)
    except RuntimeError as err:
        write_skill_error(
            str(err), 3, error_type="ApiError",
            output_format=fmt, script_name="check_existing_pr_for_issue.py",
        )
        raise SystemExit(3) from err

    data = {
        "issue": args.issue,
        "existing_pr_count": len(matches),
        "existing_prs": matches,
    }
    if matches:
        summary = ", ".join(f"#{m['number']}" for m in matches)
        write_skill_error(
            f"Issue #{args.issue} already has open PR(s): {summary}. "
            "Do not open a duplicate; coordinate on the existing PR.",
            1, error_type="DuplicateWork",
            output_format=fmt, script_name="check_existing_pr_for_issue.py",
            extra=data,
        )
        raise SystemExit(1)

    write_skill_output(
        data, output_format=fmt,
        human_summary=f"No open PR references issue #{args.issue}; safe to proceed.",
        status="PASS", script_name="check_existing_pr_for_issue.py",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
