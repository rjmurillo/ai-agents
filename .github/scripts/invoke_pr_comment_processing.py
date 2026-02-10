#!/usr/bin/env python3
"""Process PR comments based on AI triage output.

Executes after ai-review action triage to:
1. Acknowledge comments (add eyes reaction)
2. Reply to comments that need responses (wontfix)
3. Flag others for human attention (stale, question, implementation)

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Parse error (JSON)
    3 - External error (API/processing errors)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys

_workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, _workspace)

from scripts.github_core.api import resolve_repo_params  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

_CODE_FENCE_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)```")


def parse_findings(json_str: str) -> dict:
    """Parse AI findings JSON, stripping markdown code fences if present.

    Returns the parsed dict. Raises SystemExit(2) on parse failure.
    """
    clean = json_str
    match = _CODE_FENCE_PATTERN.search(json_str)
    if match:
        clean = match.group(1).strip()

    try:
        parsed: dict = json.loads(clean)
        return parsed
    except json.JSONDecodeError as exc:
        preview = json_str[:500] if len(json_str) > 500 else json_str
        print(f"Failed to parse AI findings JSON: {exc}", file=sys.stderr)
        logger.debug("Raw JSON (first 500 chars): %s", preview)
        raise SystemExit(2) from exc


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------


def add_comment_reaction(
    owner: str,
    repo: str,
    comment_id: int,
    reaction: str = "eyes",
) -> bool:
    """Add a reaction to a comment.

    Tries the PR review comment endpoint first, then falls back
    to the issue comment endpoint.

    Returns True on success, False on failure.
    """
    base_url = f"repos/{owner}/{repo}"

    result = subprocess.run(
        [
            "gh",
            "api",
            f"{base_url}/pulls/comments/{comment_id}/reactions",
            "-X",
            "POST",
            "-f",
            f"content={reaction}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode == 0:
        print(f"Added {reaction} reaction to comment {comment_id}")
        return True

    result = subprocess.run(
        [
            "gh",
            "api",
            f"{base_url}/issues/comments/{comment_id}/reactions",
            "-X",
            "POST",
            "-f",
            f"content={reaction}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode == 0:
        print(f"Added {reaction} reaction to comment {comment_id}")
        return True

    error_str = result.stderr.strip() or result.stdout.strip()
    print(
        f"WARNING: Failed to add reaction to comment {comment_id}: {error_str}",
        file=sys.stderr,
    )
    return False


def reply_to_comment(
    owner: str,
    repo: str,
    pr_number: int,
    comment_id: int,
    body: str,
) -> bool:
    """Post a reply to a PR review comment.

    Uses the /replies endpoint for thread preservation.

    Returns True on success, False on failure.
    """
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{owner}/{repo}/pulls/{pr_number}/comments/{comment_id}/replies",
            "-X",
            "POST",
            "-f",
            f"body={body}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode == 0:
        print(f"Posted reply to comment {comment_id} on PR #{pr_number}")
        return True

    error_str = result.stderr.strip() or result.stdout.strip()
    print(
        f"WARNING: Failed to reply to comment {comment_id}: {error_str}",
        file=sys.stderr,
    )
    return False


# ---------------------------------------------------------------------------
# Comment processing
# ---------------------------------------------------------------------------


def process_comments(
    owner: str,
    repo: str,
    pr_number: int,
    findings: dict,
) -> dict[str, int]:
    """Process each comment based on its classification.

    Returns a stats dict with keys: acknowledged, replied, skipped, errors.
    """
    stats: dict[str, int] = {
        "acknowledged": 0,
        "replied": 0,
        "skipped": 0,
        "errors": 0,
    }

    comments = findings.get("comments", [])

    for comment in comments:
        comment_id = comment.get("id")
        if comment_id is None:
            print("WARNING: Comment missing 'id' field, skipping", file=sys.stderr)
            stats["errors"] += 1
            continue
        classification = comment.get("classification", "unknown")
        print(f"Processing comment {comment_id} [{classification}]")

        if add_comment_reaction(owner, repo, comment_id):
            stats["acknowledged"] += 1
        else:
            stats["errors"] += 1

        if classification == "stale":
            print("  Stale comment needs manual resolution (thread ID required)")
            stats["skipped"] += 1

        elif classification == "wontfix":
            resolution = comment.get("resolution")
            if not resolution:
                print(
                    "WARNING: Wontfix comment missing resolution field, cannot post reply",
                    file=sys.stderr,
                )
                stats["skipped"] += 1
                continue

            body = (
                "Thank you for the feedback. After review, "
                "we've decided not to implement this change:\n\n"
                f"{resolution}"
            )
            if reply_to_comment(owner, repo, pr_number, comment_id, body):
                stats["replied"] += 1
            else:
                stats["errors"] += 1

        elif classification == "question":
            summary = comment.get("summary", "")
            print(f"  Needs human response: {summary}")
            stats["skipped"] += 1

        elif classification in ("quick-fix", "standard", "strategic"):
            action = comment.get("action", "")
            summary = comment.get("summary", "")
            print(f"  Action needed: {action} - {summary}")
            stats["skipped"] += 1

        else:
            print(f"  Unknown classification '{classification}', skipping")
            stats["skipped"] += 1

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Process PR comments based on AI triage output. "
            "Acknowledges, replies, and flags comments for action."
        ),
    )
    parser.add_argument(
        "--pr-number",
        type=int,
        required=True,
        help="PR number to process",
    )
    parser.add_argument(
        "--verdict",
        required=True,
        help="AI verdict from ai-review action (e.g. PASS, WARN, FAIL)",
    )
    parser.add_argument(
        "--findings-json",
        required=True,
        help=("Raw JSON output from AI containing triage decisions. Use '-' to read from stdin."),
    )
    parser.add_argument(
        "--owner",
        default="",
        help="Repository owner (inferred from git remote if omitted)",
    )
    parser.add_argument(
        "--repo",
        default="",
        help="Repository name (inferred from git remote if omitted)",
    )
    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )

    parser = build_parser()
    args = parser.parse_args(argv)

    pr_number: int = args.pr_number
    verdict: str = args.verdict

    print("=== PR Comment Processing ===")
    print(f"PR Number: {pr_number}")
    print(f"Verdict: {verdict}")
    print()

    # Only process PASS or WARN verdicts
    if verdict not in ("PASS", "WARN"):
        print(
            f"WARNING: AI verdict was {verdict}, skipping comment processing",
            file=sys.stderr,
        )
        return 0

    # "-" signals stdin per Unix convention
    findings_raw: str = args.findings_json
    if findings_raw == "-":
        findings_raw = sys.stdin.read()

    findings = parse_findings(findings_raw)

    comments = findings.get("comments", [])
    if not comments:
        print("No comments to process")
        return 0

    print(f"Found {len(comments)} comments to process")
    print()

    try:
        resolved = resolve_repo_params(args.owner, args.repo)
    except SystemExit:
        raise
    except Exception as exc:
        print(
            f"Failed to resolve repository parameters: {exc}",
            file=sys.stderr,
        )
        return 1

    owner = resolved["Owner"]
    repo = resolved["Repo"]

    stats = process_comments(owner, repo, pr_number, findings)

    print()
    print("=== Processing Summary ===")
    print(f"  Acknowledged: {stats['acknowledged']}")
    print(f"  Replied: {stats['replied']}")
    print(f"  Skipped (needs human): {stats['skipped']}")
    print(f"  Errors: {stats['errors']}")

    if stats["errors"] > 0:
        print(
            f"WARNING: Completed with {stats['errors']} errors",
            file=sys.stderr,
        )
        return 3

    print("Processing complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
