#!/usr/bin/env python3
"""Extract GitHub context (PR numbers, issue numbers, owner, repo) from text and URLs.

Parses user prompts to extract GitHub context without requiring explicit parameters.
Supports text patterns ("PR 806", "#806") and GitHub URLs.

Exit codes follow ADR-035:
    0 - Success
    1 - Required context not found (when --require-pr or --require-issue specified)
"""

from __future__ import annotations

import argparse
import json
import re
import sys


def _extract_context(text: str) -> dict:
    """Extract GitHub context from text."""
    pr_numbers: list[int] = []
    issue_numbers: list[int] = []
    owner: str | None = None
    repo: str | None = None
    urls: list[dict] = []
    raw_matches: list[str] = []

    # URL extraction: github.com/owner/repo/pull/N or github.com/owner/repo/issues/N
    url_pattern = re.compile(
        r"github\.com/([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?)"
        r"/([a-zA-Z0-9._-]{1,100})/(pull|issues)/(\d+)",
        re.IGNORECASE,
    )
    url_matches = list(url_pattern.finditer(text))

    for match in url_matches:
        m_owner = match.group(1)
        m_repo = match.group(2)
        m_type = match.group(3).lower()
        m_number = int(match.group(4))

        if owner is None:
            owner = m_owner
            repo = m_repo

        url_obj = {
            "type": "PR" if m_type == "pull" else "Issue",
            "number": m_number,
            "owner": m_owner,
            "repo": m_repo,
            "url": match.group(0),
        }
        urls.append(url_obj)
        raw_matches.append(match.group(0))

        if m_type == "pull":
            if m_number not in pr_numbers:
                pr_numbers.append(m_number)
        else:
            if m_number not in issue_numbers:
                issue_numbers.append(m_number)

    # Pattern 1: "PR N", "PR #N", "PR#N"
    for match in re.finditer(r"\bPR\s*#?(\d+)\b", text, re.IGNORECASE):
        number = int(match.group(1))
        if number not in pr_numbers:
            pr_numbers.append(number)
            raw_matches.append(match.group(0))

    # Pattern 2: "pull request N", "pull request #N"
    for match in re.finditer(r"\bpull\s+request\s*#?(\d+)\b", text, re.IGNORECASE):
        number = int(match.group(1))
        if number not in pr_numbers:
            pr_numbers.append(number)
            raw_matches.append(match.group(0))

    # Pattern 3: "issue N", "issue #N", "issues N"
    for match in re.finditer(r"\bissues?\s*#?(\d+)\b", text, re.IGNORECASE):
        number = int(match.group(1))
        if number not in issue_numbers:
            issue_numbers.append(number)
            raw_matches.append(match.group(0))

    # Pattern 4: Standalone "#N" (ambiguous, defaults to PR)
    for match in re.finditer(r"(?<!/)#(\d+)\b", text):
        number = int(match.group(1))
        match_pos = match.start()

        in_url = False
        for url_match in url_matches:
            if url_match.start() <= match_pos < url_match.end():
                in_url = True
                break

        if not in_url:
            if number not in pr_numbers and number not in issue_numbers:
                pr_numbers.append(number)
                raw_matches.append(match.group(0))

    return {
        "pr_numbers": pr_numbers,
        "issue_numbers": issue_numbers,
        "owner": owner,
        "repo": repo,
        "urls": urls,
        "raw_matches": raw_matches,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract GitHub context from text and URLs.",
    )
    parser.add_argument("--text", required=True, help="Text to parse for GitHub context")
    parser.add_argument(
        "--require-pr",
        action="store_true",
        help="Fail if no PR number can be extracted",
    )
    parser.add_argument(
        "--require-issue",
        action="store_true",
        help="Fail if no issue number can be extracted",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    result = _extract_context(args.text)

    if args.require_pr and not result["pr_numbers"]:
        print(
            "Cannot extract PR number from prompt. Provide explicit PR number or URL.",
            file=sys.stderr,
        )
        return 1

    if args.require_issue and not result["issue_numbers"]:
        print(
            "Cannot extract issue number from prompt. Provide explicit issue number or URL.",
            file=sys.stderr,
        )
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
