#!/usr/bin/env python3
"""Process PR comments based on AI triage findings.

Acknowledges comments with reactions and posts replies based on
structured findings JSON from an AI triage step.

Exit codes (ADR-035):
    0 = Success (all comments processed)
    1 = Invalid parameters or partial failure
    3 = API error
    4 = Not authenticated
"""

import argparse
import json
import os
import subprocess
import sys

_lib_dir = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.join(os.getcwd(), ".claude")),
    "skills", "github", "lib",
)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    resolve_repo_params,
    write_error_and_exit,
)


def strip_code_fences(text: str) -> str:
    """Remove markdown code fence wrapping from JSON text."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        # Remove opening fence (```json or ```)
        lines = lines[1:]
        # Remove closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def parse_findings(raw: str) -> list[dict]:
    """Parse findings JSON, handling code fence wrapping."""
    cleaned = strip_code_fences(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        write_error_and_exit(f"Invalid findings JSON: {e}", 1)
        # write_error_and_exit calls sys.exit; unreachable
        raise SystemExit(1) from e

    if isinstance(parsed, dict):
        # Accept {"findings": [...]} or {"comments": [...]} wrappers
        for key in ("findings", "comments", "items"):
            if key in parsed and isinstance(parsed[key], list):
                return list(parsed[key])
        # Single finding wrapped in a dict
        return [parsed]
    if isinstance(parsed, list):
        return list(parsed)
    write_error_and_exit(
        "Findings JSON must be an array or object with a findings array", 1,
    )
    # write_error_and_exit calls sys.exit; unreachable
    raise SystemExit(1)


def acknowledge_comment(owner: str, repo: str, comment_id: int) -> bool:
    """Add an eyes reaction to a PR review comment."""
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/pulls/comments/{comment_id}/reactions",
            "-X", "POST", "--input", "-",
        ],
        input=json.dumps({"content": "eyes"}),
        capture_output=True, text=True,
    )
    return result.returncode == 0


def reply_to_comment(owner: str, repo: str, pr_number: int, comment_id: int, body: str) -> bool:
    """Reply to a PR review comment."""
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/pulls/{pr_number}/comments/{comment_id}/replies",
            "-X", "POST", "--input", "-",
        ],
        input=json.dumps({"body": body}),
        capture_output=True, text=True,
    )
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Process PR comments from AI triage")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pr-number", type=int, required=True, help="PR number")
    parser.add_argument("--verdict", required=True, help="Overall triage verdict")
    parser.add_argument("--findings-json", required=True, help="Raw JSON string of findings")
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved["owner"]
    repo = resolved["repo"]

    findings = parse_findings(args.findings_json)

    acknowledged = 0
    replied = 0
    errors: list[str] = []

    for finding in findings:
        comment_id = finding.get("comment_id") or finding.get("id") or finding.get("commentId")
        if not comment_id:
            errors.append("Finding missing comment_id field")
            continue

        comment_id = int(comment_id)

        # Acknowledge with eyes reaction
        if acknowledge_comment(owner, repo, comment_id):
            acknowledged += 1
        else:
            errors.append(f"Failed to react to comment {comment_id}")

        # Reply if finding includes a reply body
        reply_body = finding.get("reply") or finding.get("response") or finding.get("body")
        if reply_body:
            if reply_to_comment(owner, repo, args.pr_number, comment_id, reply_body):
                replied += 1
            else:
                errors.append(f"Failed to reply to comment {comment_id}")

    processed = len(findings)
    success = len(errors) == 0

    output = {
        "Success": success,
        "PullRequest": args.pr_number,
        "Verdict": args.verdict,
        "ProcessedComments": processed,
        "Acknowledged": acknowledged,
        "Replied": replied,
        "Errors": errors,
    }

    print(json.dumps(output, indent=2))

    print(
        f"PR #{args.pr_number} comment processing: "
        f"{processed} processed, {acknowledged} acknowledged, "
        f"{replied} replied",
        file=sys.stderr,
    )
    if errors:
        for err in errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
