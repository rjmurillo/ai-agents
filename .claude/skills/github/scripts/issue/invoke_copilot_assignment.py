#!/usr/bin/env python3
"""Synthesize context and assign GitHub Copilot to an issue.

Fetches issue comments, extracts context from trusted sources,
generates a synthesis comment with @copilot mention, and assigns
copilot-swe-agent. Idempotent: updates existing synthesis comment
if marker is detected.

Exit codes (ADR-035):
    0 = Success (includes idempotent update)
    1 = Invalid parameters
    2 = Issue not found
    3 = API error
    4 = Not authenticated
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

_lib_dir = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.join(os.getcwd(), ".claude")),
    "skills", "github", "lib",
)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    _run_gh,
    assert_gh_authenticated,
    resolve_repo_params,
    write_error_and_exit,
)

DEFAULT_CONFIG = {
    "trusted_sources": {
        "maintainers": ["rjmurillo"],
        "ai_agents": [
            "rjmurillo-bot", "Copilot", "coderabbitai[bot]",
            "cursor[bot]", "github-actions[bot]",
        ],
    },
    "extraction_patterns": {
        "coderabbit": {
            "username": "coderabbitai[bot]",
            "implementation_plan": "## Implementation",
            "related_issues": "Related Issues",
            "related_prs": "Related PRs",
        },
        "ai_triage": {
            "marker": "<!-- AI-ISSUE-TRIAGE -->",
        },
    },
    "synthesis": {
        "marker": "<!-- COPILOT-CONTEXT-SYNTHESIS -->",
    },
}


def _get_comments(owner: str, repo: str, issue_number: int) -> list:
    """Fetch all comments for an issue."""
    result = _run_gh(
        "api", f"repos/{owner}/{repo}/issues/{issue_number}/comments",
        check=False,
    )
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def _filter_trusted(comments: list, trusted_users: list[str]) -> list:
    """Filter comments to only those from trusted sources."""
    return [
        c for c in comments
        if c.get("user", {}).get("login") in trusted_users
    ]


def get_maintainer_guidance(
    comments: list, maintainers: list[str],
) -> list[str]:
    """Extract key decisions from maintainer comments."""
    maintainer_comments = [
        c for c in comments
        if c.get("user", {}).get("login") in maintainers
    ]
    if not maintainer_comments:
        return []

    guidance = []
    for comment in maintainer_comments:
        body = comment.get("body", "")
        lines = body.split("\n")
        found_bullets = False

        for line in lines:
            trimmed = line.strip()
            match = (
                re.match(r"^\d+\.\s+(.+)$", trimmed)
                or re.match(r"^[-*]\s+(.+)$", trimmed)
            )
            if match:
                item = match.group(1)
                if len(item) > 10 and not re.match(r"^\[[ x]\]", item):
                    guidance.append(item)
                    found_bullets = True

        if not found_bullets:
            sentences = re.split(r"(?<=[.!?])\s+", body)
            for sentence in sentences:
                cleaned = re.sub(r"[\r\n]+", " ", sentence).strip()
                if (
                    re.search(
                        r"\b(MUST|SHOULD|SHALL|REQUIRED|RECOMMENDED)\b",
                        cleaned, re.IGNORECASE,
                    )
                    and len(cleaned) > 15
                ):
                    guidance.append(cleaned)

    return guidance


def get_coderabbit_plan(comments: list, patterns: dict) -> dict | None:
    """Extract implementation plan from CodeRabbit comments."""
    username = patterns.get("username", "coderabbitai[bot]")
    rabbit_comments = [
        c for c in comments
        if c.get("user", {}).get("login") == username
    ]
    if not rabbit_comments:
        return None

    plan: dict = {
        "Implementation": None,
        "RelatedIssues": [],
        "RelatedPRs": [],
    }

    impl_pattern = re.escape(patterns.get("implementation_plan", "## Implementation"))

    for comment in rabbit_comments:
        body = comment.get("body", "")

        impl_match = re.search(
            rf"{impl_pattern}([\s\S]*?)(?=##|$)", body
        )
        if impl_match:
            plan["Implementation"] = impl_match.group(1).strip()

        issue_matches = re.findall(r"/issues/(\d+)|#(\d+)", body)
        for m in issue_matches:
            num = m[0] or m[1]
            ref = f"#{num}"
            if ref not in plan["RelatedIssues"]:
                plan["RelatedIssues"].append(ref)

        pr_matches = re.findall(r"/pull/(\d+)", body)
        for m in pr_matches:
            ref = f"#{m}"
            if ref not in plan["RelatedPRs"]:
                plan["RelatedPRs"].append(ref)

    return plan


def get_ai_triage_info(comments: list, triage_marker: str) -> dict | None:
    """Extract triage information from AI Triage comments."""
    escaped_marker = re.escape(triage_marker)
    triage_comment = None
    for c in comments:
        if re.search(escaped_marker, c.get("body", "")):
            triage_comment = c
            break

    if not triage_comment:
        return None

    triage: dict = {"Priority": None, "Category": None}
    body = triage_comment.get("body", "")

    for field in ("Priority", "Category"):
        table_match = re.search(
            rf"^\s*\|\s*\*\*{field}\*\*\s*\|\s*`([^`]+)`",
            body, re.MULTILINE,
        )
        if table_match:
            triage[field] = table_match.group(1).strip()
        else:
            plain_match = re.search(
                rf"^{field}[:\s]+(\S+)", body, re.MULTILINE
            )
            if plain_match:
                triage[field] = plain_match.group(1)

    return triage


def has_synthesizable_content(
    maintainer_guidance: list,
    coderabbit_plan: dict | None,
    ai_triage: dict | None,
) -> bool:
    """Check if there is any content worth synthesizing."""
    if maintainer_guidance:
        return True

    if ai_triage:
        p = ai_triage.get("Priority")
        c = ai_triage.get("Category")
        if (p and str(p).strip()) or (c and str(c).strip()):
            return True

    if coderabbit_plan:
        if coderabbit_plan.get("Implementation"):
            return True
        if coderabbit_plan.get("RelatedIssues"):
            return True
        if coderabbit_plan.get("RelatedPRs"):
            return True

    return False


def build_synthesis_comment(
    marker: str,
    maintainer_guidance: list,
    coderabbit_plan: dict | None,
    ai_triage: dict | None,
) -> str:
    """Generate the synthesis comment body."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    body = f"{marker}\n\n@copilot Here is synthesized context for this issue:\n"

    if maintainer_guidance:
        body += "\n## Maintainer Guidance\n\n"
        for item in maintainer_guidance[:10]:
            body += f"- {item}\n"

    has_ai = False
    if coderabbit_plan and (
        coderabbit_plan.get("Implementation")
        or coderabbit_plan.get("RelatedIssues")
        or coderabbit_plan.get("RelatedPRs")
    ):
        has_ai = True
    if ai_triage:
        has_ai = True

    if has_ai:
        body += "\n## AI Agent Recommendations\n\n"
        if ai_triage:
            if ai_triage.get("Priority"):
                body += f"- **Priority**: {ai_triage['Priority']}\n"
            if ai_triage.get("Category"):
                body += f"- **Category**: {ai_triage['Category']}\n"
        if coderabbit_plan:
            if coderabbit_plan.get("RelatedIssues"):
                issues = ", ".join(coderabbit_plan["RelatedIssues"])
                body += f"- **Related Issues**: {issues}\n"
            if coderabbit_plan.get("RelatedPRs"):
                prs = ", ".join(coderabbit_plan["RelatedPRs"])
                body += f"- **Related PRs**: {prs}\n"
            if coderabbit_plan.get("Implementation"):
                body += (
                    f"\n**CodeRabbit Implementation Plan**:\n"
                    f"{coderabbit_plan['Implementation']}\n"
                )

    body += f"\n---\n*Generated: {timestamp}*"
    return body


def find_existing_synthesis(comments: list, marker: str) -> dict | None:
    """Find existing synthesis comment by marker."""
    escaped = re.escape(marker)
    for c in comments:
        if re.search(escaped, c.get("body", "")):
            return c
    return None


def create_context_file(
    issue: dict, trusted_comments: list, issue_number: int,
) -> str:
    """Create a context file for AI synthesis."""
    labels = ", ".join(
        label.get("name", "") for label in issue.get("labels", [])
    )
    content = (
        f"# Issue Context for Synthesis\n\n"
        f"## Issue Details\n\n"
        f"**Title**: {issue.get('title', '')}\n"
        f"**Labels**: {labels}\n\n"
        f"### Description\n\n"
        f"{issue.get('body', '')}\n\n"
        f"## Comments from Trusted Sources\n\n"
    )

    for comment in trusted_comments:
        login = comment.get("user", {}).get("login", "unknown")
        body = comment.get("body", "")
        content += (
            f"### Comment by {login}\n\n"
            f"{body}\n\n---\n\n"
        )

    context_file = os.path.join(
        tempfile.gettempdir(), f"issue-{issue_number}-context.md"
    )
    with open(context_file, "w", encoding="utf-8") as f:
        f.write(content)

    return context_file


def invoke_copilot_assignment(
    owner: str,
    repo: str,
    issue_number: int,
    skip_assignment: bool = False,
    prepare_context_only: bool = False,
    dry_run: bool = False,
) -> dict:
    """Synthesize context and assign Copilot to an issue.

    Args:
        owner: Repository owner.
        repo: Repository name.
        issue_number: Issue number.
        skip_assignment: Skip copilot-swe-agent assignment.
        prepare_context_only: Only prepare context file, no posting.
        dry_run: Preview without posting or assigning.

    Returns:
        Dict with operation result.
    """
    config = DEFAULT_CONFIG

    # Fetch issue details
    result = _run_gh(
        "api", f"repos/{owner}/{repo}/issues/{issue_number}",
        check=False,
    )
    if result.returncode != 0:
        if "Not Found" in result.stdout or "Not Found" in result.stderr:
            write_error_and_exit(
                f"Issue #{issue_number} not found in {owner}/{repo}", 2
            )
        write_error_and_exit(
            f"Failed to get issue: {result.stderr}", 3
        )

    issue = json.loads(result.stdout)

    comments = _get_comments(owner, repo, issue_number)
    trusted_users = (
        config["trusted_sources"]["maintainers"]
        + config["trusted_sources"]["ai_agents"]
    )
    trusted_comments = _filter_trusted(comments, trusted_users)

    if prepare_context_only:
        context_file = create_context_file(
            issue, trusted_comments, issue_number
        )
        existing = find_existing_synthesis(
            comments, config["synthesis"]["marker"]
        )
        return {
            "Success": True,
            "ContextFile": context_file,
            "ExistingSynthesisId": existing["id"] if existing else None,
            "Marker": config["synthesis"]["marker"],
            "IssueNumber": issue_number,
            "Owner": owner,
            "Repo": repo,
        }

    maintainer_guidance = get_maintainer_guidance(
        trusted_comments, config["trusted_sources"]["maintainers"]
    )
    coderabbit_plan = get_coderabbit_plan(
        trusted_comments,
        config["extraction_patterns"]["coderabbit"],
    )
    ai_triage = get_ai_triage_info(
        trusted_comments,
        config["extraction_patterns"]["ai_triage"]["marker"],
    )

    has_content = has_synthesizable_content(
        maintainer_guidance, coderabbit_plan, ai_triage
    )
    existing = find_existing_synthesis(
        comments, config["synthesis"]["marker"]
    )

    if dry_run:
        return {
            "Success": True,
            "Action": "DryRun",
            "HasContent": has_content,
            "ExistingSynthesisId": existing["id"] if existing else None,
            "IssueNumber": issue_number,
        }

    action = "Skipped"
    comment_id = None
    comment_url = None

    if has_content:
        synthesis_body = build_synthesis_comment(
            config["synthesis"]["marker"],
            maintainer_guidance, coderabbit_plan, ai_triage,
        )

        if existing:
            response = subprocess.run(
                [
                    "gh", "api",
                    f"repos/{owner}/{repo}/issues/comments/{existing['id']}",
                    "-X", "PATCH", "-f", f"body={synthesis_body}",
                ],
                capture_output=True,
                text=True,
            )
            if response.returncode == 0:
                data = json.loads(response.stdout)
                comment_id = data.get("id")
                comment_url = data.get("html_url")
                action = "Updated"
        else:
            response = subprocess.run(
                [
                    "gh", "api",
                    f"repos/{owner}/{repo}/issues/{issue_number}/comments",
                    "-X", "POST", "-f", f"body={synthesis_body}",
                ],
                capture_output=True,
                text=True,
            )
            if response.returncode == 0:
                data = json.loads(response.stdout)
                comment_id = data.get("id")
                comment_url = data.get("html_url")
                action = "Created"

    assigned = False
    if not skip_assignment:
        assign_result = subprocess.run(
            [
                "gh", "issue", "edit", str(issue_number),
                "--repo", f"{owner}/{repo}",
                "--add-assignee", "copilot-swe-agent",
            ],
            capture_output=True,
            text=True,
        )
        assigned = assign_result.returncode == 0

    return {
        "Success": True,
        "Action": action,
        "IssueNumber": issue_number,
        "CommentId": comment_id,
        "CommentUrl": comment_url,
        "Assigned": assigned,
        "Marker": config["synthesis"]["marker"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synthesize context and assign Copilot to an issue"
    )
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument(
        "--issue-number", type=int, required=True, help="Issue number"
    )
    parser.add_argument(
        "--skip-assignment", action="store_true",
        help="Skip copilot-swe-agent assignment",
    )
    parser.add_argument(
        "--prepare-context-only", action="store_true",
        help="Only prepare context file, do not post",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview without posting or assigning",
    )
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)

    output = invoke_copilot_assignment(
        resolved["owner"], resolved["repo"], args.issue_number,
        skip_assignment=args.skip_assignment,
        prepare_context_only=args.prepare_context_only,
        dry_run=args.dry_run,
    )

    print(json.dumps(output, indent=2))
    action = output.get("Action", "")
    print(
        f"Issue #{args.issue_number}: {action}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
