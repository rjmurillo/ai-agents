#!/usr/bin/env python3
"""Extract GitHub context (PR numbers, issue numbers, owner, repo) from text.

Parses user prompts to extract GitHub context without requiring
explicit parameters. Supports text patterns and GitHub URLs.

Exit codes (ADR-035):
    0 = Success
    1 = Required context not found
"""

import argparse
import json
import os
import re
import sys

_lib_dir = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.join(os.getcwd(), ".claude")),
    "skills", "github", "lib",
)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)


def extract_github_context(
    text: str,
    require_pr: bool = False,
    require_issue: bool = False,
) -> dict:
    """Extract GitHub context from text.

    Args:
        text: Text to parse for GitHub context.
        require_pr: Fail if no PR number found.
        require_issue: Fail if no issue number found.

    Returns:
        Dict with PRNumbers, IssueNumbers, Owner, Repo, URLs, RawMatches.
    """
    result: dict = {
        "PRNumbers": [],
        "IssueNumbers": [],
        "Owner": None,
        "Repo": None,
        "URLs": [],
        "RawMatches": [],
    }

    # URL extraction
    url_pattern = (
        r"github\.com/"
        r"([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?)/"
        r"([a-zA-Z0-9._-]{1,100})/"
        r"(pull|issues)/(\d+)"
    )
    url_matches = list(re.finditer(url_pattern, text, re.IGNORECASE))

    for match in url_matches:
        owner = match.group(1)
        repo = match.group(2)
        item_type = match.group(3).lower()
        number = int(match.group(4))

        if result["Owner"] is None:
            result["Owner"] = owner
            result["Repo"] = repo

        url_obj = {
            "Type": "PR" if item_type == "pull" else "Issue",
            "Number": number,
            "Owner": owner,
            "Repo": repo,
            "URL": match.group(0),
        }
        result["URLs"].append(url_obj)
        result["RawMatches"].append(match.group(0))

        target = "PRNumbers" if item_type == "pull" else "IssueNumbers"
        if number not in result[target]:
            result[target].append(number)

    # PR patterns: "PR N", "PR #N", "PR#N"
    for match in re.finditer(r"\bPR\s*#?(\d+)\b", text, re.IGNORECASE):
        number = int(match.group(1))
        if number not in result["PRNumbers"]:
            result["PRNumbers"].append(number)
            result["RawMatches"].append(match.group(0))

    # "pull request N", "pull request #N"
    for match in re.finditer(
        r"\bpull\s+request\s*#?(\d+)\b", text, re.IGNORECASE,
    ):
        number = int(match.group(1))
        if number not in result["PRNumbers"]:
            result["PRNumbers"].append(number)
            result["RawMatches"].append(match.group(0))

    # "issue N", "issue #N", "issues N"
    for match in re.finditer(r"\bissues?\s*#?(\d+)\b", text, re.IGNORECASE):
        number = int(match.group(1))
        if number not in result["IssueNumbers"]:
            result["IssueNumbers"].append(number)
            result["RawMatches"].append(match.group(0))

    # Standalone "#N" (ambiguous, defaults to PR)
    url_ranges = [(m.start(), m.start() + len(m.group(0))) for m in url_matches]
    for match in re.finditer(r"(?<!/)#(\d+)\b", text):
        number = int(match.group(1))
        pos = match.start()

        in_url = any(start <= pos < end for start, end in url_ranges)
        if in_url:
            continue

        if (
            number not in result["PRNumbers"]
            and number not in result["IssueNumbers"]
        ):
            result["PRNumbers"].append(number)
            result["RawMatches"].append(match.group(0))

    # Validation
    if require_pr and not result["PRNumbers"]:
        print(
            "Error: Cannot extract PR number from prompt. "
            "Provide explicit PR number or URL.",
            file=sys.stderr,
        )
        sys.exit(1)

    if require_issue and not result["IssueNumbers"]:
        print(
            "Error: Cannot extract issue number from prompt. "
            "Provide explicit issue number or URL.",
            file=sys.stderr,
        )
        sys.exit(1)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract GitHub context from text and URLs"
    )
    parser.add_argument(
        "--text", required=True, help="Text to parse for GitHub context"
    )
    parser.add_argument(
        "--require-pr", action="store_true",
        help="Fail if no PR number found",
    )
    parser.add_argument(
        "--require-issue", action="store_true",
        help="Fail if no issue number found",
    )
    args = parser.parse_args()

    output = extract_github_context(
        args.text, args.require_pr, args.require_issue,
    )

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
