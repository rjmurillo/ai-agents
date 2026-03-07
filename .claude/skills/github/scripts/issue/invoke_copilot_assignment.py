#!/usr/bin/env python3
"""Synthesize context and assign GitHub Copilot to an issue.

Fetches issue comments, extracts context from trusted sources (maintainers, AI agents),
generates a synthesis comment with @copilot mention, and assigns copilot-swe-agent.

Idempotent: If a synthesis comment already exists (detected via marker), it updates
the existing comment rather than creating a duplicate.

Exit codes follow ADR-035:
    0 - Success (includes idempotent update)
    1 - Invalid parameters / logic error
    2 - Issue not found
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
import tempfile
from datetime import UTC, datetime
from pathlib import Path

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
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    create_issue_comment,
    error_and_exit,
    get_issue_comments,
    get_trusted_source_comments,
    resolve_repo_params,
    update_issue_comment,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG: dict = {
    "trusted_sources": {
        "maintainers": [],
        "ai_agents": [],
    },
    "extraction_patterns": {
        "coderabbit": {
            "username": "coderabbitai[bot]",
            "implementation_plan": "## Implementation",
            "related_issues": "Similar Issues",
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


def _extract_yaml_list(content: str, key: str) -> list[str]:
    """Extract items from a simple YAML list block, avoiding ReDoS-prone patterns.

    Parses line-by-line: finds the key, collects indented ``- value`` items,
    stops at the next top-level key or end of content.
    """
    items: list[str] = []
    in_block = False
    key_pattern = re.compile(rf"^{re.escape(key)}:")
    item_pattern = re.compile(r"^[ \t]+-[ \t]+(.*)")
    for line in content.split("\n"):
        if key_pattern.match(line):
            in_block = True
            continue
        if in_block:
            m = item_pattern.match(line)
            if m:
                items.append(m.group(1))
            elif line.strip() and not line[0].isspace():
                break
    return items


def _load_synthesis_config(config_path: str) -> dict:
    """Load copilot-synthesis.yml configuration or return empty defaults.

    When the config file is missing, returns empty trusted_sources lists.
    Callers must validate that required lists are populated before use.
    """
    if not config_path:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                repo_root = result.stdout.strip()
                config_path = os.path.join(
                    repo_root, ".claude", "skills", "github", "copilot-synthesis.yml",
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    if not config_path or not Path(config_path).exists():
        return _DEFAULT_CONFIG

    try:
        content = Path(config_path).read_text(encoding="utf-8")
        config: dict = json.loads(json.dumps(_DEFAULT_CONFIG))

        # Extract maintainers (line-by-line to avoid ReDoS)
        config["trusted_sources"]["maintainers"] = [
            v.split()[0]
            for v in _extract_yaml_list(content, "maintainers")
            if v.strip()
        ]

        # Extract ai_agents (line-by-line to avoid ReDoS, strip inline comments)
        config["trusted_sources"]["ai_agents"] = [
            cleaned
            for v in _extract_yaml_list(content, "ai_agents")
            if (cleaned := re.sub(r"\s*#.*$", "", v).strip())
        ]

        # Extract coderabbit username
        m = re.search(r'coderabbit:[\s\S]*?username:\s*"([^"]+)"', content)
        if m:
            config["extraction_patterns"]["coderabbit"]["username"] = m.group(1)

        # Extract synthesis marker
        m = re.search(r'(?s)synthesis:.*?marker:\s*"([^"]+)"', content)
        if m:
            config["synthesis"]["marker"] = m.group(1)

        return config
    except Exception:
        return _DEFAULT_CONFIG


# ---------------------------------------------------------------------------
# Context Extraction
# ---------------------------------------------------------------------------


def _get_maintainer_guidance(
    comments: list[dict], maintainers: list[str],
) -> list[str]:
    """Extract key decisions from maintainer comments.

    Uses a tiered approach:
    1. Extract explicit bullet points and numbered items
    2. If none found, extract sentences with RFC 2119 keywords (MUST, SHOULD, etc.)
    """
    maintainer_comments = [
        c for c in comments if c.get("user", {}).get("login") in maintainers
    ]
    if not maintainer_comments:
        return []

    guidance: list[str] = []
    for comment in maintainer_comments:
        lines = comment.get("body", "").split("\n")
        found_bullets = False

        for line in lines:
            trimmed = line.strip()
            m = re.match(r"^\d+\.\s+(.+)$", trimmed) or re.match(r"^[-*]\s+(.+)$", trimmed)
            if m:
                item = m.group(1)
                if len(item) > 10 and not re.match(r"^\[[ x]\]", item):
                    guidance.append(item)
                    found_bullets = True

        if not found_bullets:
            sentences = re.split(r"(?<=[.!?])\s+", comment.get("body", ""))
            for sentence in sentences:
                cleaned = re.sub(r"[\r\n]+", " ", sentence.strip())
                pattern = r"\b(MUST|SHOULD|SHALL|REQUIRED|RECOMMENDED)\b"
                if (
                    re.search(pattern, cleaned, re.IGNORECASE)
                    and len(cleaned) > 15
                ):
                    guidance.append(cleaned)

    return guidance


def _get_coderabbit_plan(
    comments: list[dict], patterns: dict,
) -> dict | None:
    """Extract implementation plan from CodeRabbit comments."""
    rabbit_comments = [
        c for c in comments if c.get("user", {}).get("login") == patterns["username"]
    ]
    if not rabbit_comments:
        return None

    plan: dict = {"implementation": None, "related_issues": [], "related_prs": []}

    impl_pattern = re.escape(patterns["implementation_plan"])
    issues_raw = re.escape(patterns["related_issues"])
    prs_raw = re.escape(patterns["related_prs"])

    issues_pattern = f"(?:<b>)?{issues_raw}(?:</b>)?"
    prs_pattern = f"(?:<b>)?{prs_raw}(?:</b>)?"

    for comment in rabbit_comments:
        body = comment.get("body", "")

        m = re.search(f"{impl_pattern}([\\s\\S]*?)(?=##|$)", body)
        if m:
            plan["implementation"] = m.group(1).strip()

        m = re.search(
            f"{issues_pattern}([\\s\\S]*?)(?=</details>|<details>|##|$)",
            body,
        )
        if m:
            issue_matches = re.findall(r"/issues/(\d+)|#(\d+)", m.group(1))
            plan["related_issues"] = list({
                f"#{g1 or g2}" for g1, g2 in issue_matches
            })

        m = re.search(
            f"{prs_pattern}([\\s\\S]*?)(?=</details>|<details>|##|$)",
            body,
        )
        if m:
            pr_matches = re.findall(r"/pull/(\d+)|#(\d+)", m.group(1))
            plan["related_prs"] = list({
                f"#{g1 or g2}" for g1, g2 in pr_matches
            })

    return plan


def _get_ai_triage_info(
    comments: list[dict], triage_marker: str,
) -> dict | None:
    """Extract triage information from AI Triage comments."""
    escaped_marker = re.escape(triage_marker)
    triage_comment = None
    for c in comments:
        if re.search(escaped_marker, c.get("body", "")):
            triage_comment = c
            break

    if not triage_comment:
        return None

    triage: dict[str, str | None] = {"priority": None, "category": None}
    body = triage_comment.get("body", "")

    for field in ("Priority", "Category"):
        m = re.search(
            rf"(?m)^\s*\|\s*\*\*{field}\*\*\s*\|\s*`([^`]+)`",
            body,
        )
        if m:
            triage[field.lower()] = m.group(1).strip()
        else:
            m = re.search(rf"(?m)^{field}[:\s]+(\S+)", body)
            if m:
                triage[field.lower()] = m.group(1)

    return triage


# ---------------------------------------------------------------------------
# Synthesis Generation
# ---------------------------------------------------------------------------


def _has_synthesizable_content(
    maintainer_guidance: list[str],
    coderabbit_plan: dict | None,
    ai_triage: dict | None,
) -> bool:
    """Check if there is content worth synthesizing."""
    if maintainer_guidance:
        return True

    if ai_triage:
        if ai_triage.get("priority") or ai_triage.get("category"):
            return True

    if coderabbit_plan:
        if (
            coderabbit_plan.get("implementation")
            or coderabbit_plan.get("related_issues")
            or coderabbit_plan.get("related_prs")
        ):
            return True

    return False


def _build_synthesis_comment(
    marker: str,
    maintainer_guidance: list[str],
    coderabbit_plan: dict | None,
    ai_triage: dict | None,
) -> str:
    """Generate the synthesis comment body."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    body = f"{marker}\n\n@copilot Here is synthesized context for this issue:\n"

    if maintainer_guidance:
        body += "\n## Maintainer Guidance\n\n"
        for item in maintainer_guidance[:10]:
            body += f"- {item}\n"

    has_ai_content = False
    if coderabbit_plan and (
        coderabbit_plan.get("implementation")
        or coderabbit_plan.get("related_issues")
        or coderabbit_plan.get("related_prs")
    ):
        has_ai_content = True
    if ai_triage:
        has_ai_content = True

    if has_ai_content:
        body += "\n## AI Agent Recommendations\n\n"

        if ai_triage:
            if ai_triage.get("priority"):
                body += f"- **Priority**: {ai_triage['priority']}\n"
            if ai_triage.get("category"):
                body += f"- **Category**: {ai_triage['category']}\n"

        if coderabbit_plan:
            if coderabbit_plan.get("related_issues"):
                body += f"- **Related Issues**: {', '.join(coderabbit_plan['related_issues'])}\n"
            if coderabbit_plan.get("related_prs"):
                body += f"- **Related PRs**: {', '.join(coderabbit_plan['related_prs'])}\n"
            if coderabbit_plan.get("implementation"):
                impl = coderabbit_plan['implementation']
                body += f"\n**CodeRabbit Implementation Plan**:\n{impl}\n"

    body += f"\n---\n*Generated: {timestamp}*"
    return body


def _find_existing_synthesis(
    comments: list[dict], marker: str,
) -> dict | None:
    """Find existing synthesis comment by marker."""
    escaped = re.escape(marker)
    for c in comments:
        if re.search(escaped, c.get("body", "")):
            return c
    return None


def _assign_copilot(owner: str, repo: str, issue_number: int) -> bool:
    """Assign copilot-swe-agent to the issue."""
    result = subprocess.run(
        [
            "gh", "issue", "edit", str(issue_number),
            "--repo", f"{owner}/{repo}",
            "--add-assignee", "copilot-swe-agent",
        ],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"WARNING: Failed to assign copilot-swe-agent: {result.stderr}", file=sys.stderr)
        return False
    return True


def _create_context_file(
    issue: dict, trusted_comments: list[dict], issue_number: int,
) -> str:
    """Create a context file for AI synthesis."""
    context_file = os.path.join(tempfile.gettempdir(), f"issue-{issue_number}-context.md")

    labels_str = ", ".join(label["name"] for label in issue.get("labels", []))
    content = f"""# Issue Context for Synthesis

## Issue Details

**Title**: {issue.get('title', '')}
**Labels**: {labels_str}

### Description

{issue.get('body', '')}

## Comments from Trusted Sources

"""
    for comment in trusted_comments:
        login = comment.get("user", {}).get("login", "unknown")
        comment_body = comment.get("body", "")
        content += f"""
### Comment by {login}

{comment_body}

---

"""

    Path(context_file).write_text(content, encoding="utf-8")
    return context_file


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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synthesize context and assign GitHub Copilot to an issue.",
    )
    parser.add_argument("--issue-number", type=int, required=True, help="Issue number")
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--config-path",
        default="",
        help="Path to copilot-synthesis.yml config file",
    )
    parser.add_argument(
        "--skip-assignment",
        action="store_true",
        help="Skip copilot-swe-agent assignment",
    )
    parser.add_argument(
        "--prepare-context-only",
        action="store_true",
        help="Only prepare the context file for AI synthesis",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview synthesis comment without posting or assigning",
    )
    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:  # noqa: C901 - faithful port of complex PS1
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    issue_number: int = args.issue_number

    print(f"Processing issue #{issue_number} in {owner}/{repo}")

    config = _load_synthesis_config(args.config_path)

    trusted = config["trusted_sources"]
    if not trusted["maintainers"] and not trusted["ai_agents"]:
        error_and_exit(
            "No trusted sources configured. "
            "Create a copilot-synthesis.yml with maintainers and ai_agents lists. "
            "See .claude/skills/github/copilot-synthesis.yml for the expected format.",
            2,
        )

    # Fetch issue details
    issue_result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/issues/{issue_number}"],
        capture_output=True, text=True, check=False,
    )
    if issue_result.returncode != 0:
        error_str = issue_result.stderr.strip() or issue_result.stdout.strip()
        if "Not Found" in error_str:
            error_and_exit(f"Issue #{issue_number} not found in {owner}/{repo}", 2)
        error_and_exit(f"Failed to get issue: {error_str}", 3)

    issue = json.loads(issue_result.stdout)
    print(f"Issue: {issue.get('title', '')}")

    # Fetch comments
    comments = get_issue_comments(owner, repo, issue_number)
    print(f"Found {len(comments)} comments")

    trusted_users = (
        config["trusted_sources"]["maintainers"]
        + config["trusted_sources"]["ai_agents"]
    )
    trusted_comments = get_trusted_source_comments(comments, trusted_users)
    print(f"Found {len(trusted_comments)} comments from trusted sources")

    # PrepareContextOnly mode
    if args.prepare_context_only:
        context_file = _create_context_file(issue, trusted_comments, issue_number)
        existing_synthesis = _find_existing_synthesis(comments, config["synthesis"]["marker"])

        output = {
            "context_file": context_file,
            "existing_synthesis_id": existing_synthesis["id"] if existing_synthesis else None,
            "marker": config["synthesis"]["marker"],
            "issue_number": issue_number,
            "owner": owner,
            "repo": repo,
        }
        print(json.dumps(output, indent=2))

        _write_github_output({
            "context_file": context_file,
            "existing_synthesis_id": str(output["existing_synthesis_id"] or ""),
            "marker": config["synthesis"]["marker"],
        })
        return 0

    # Extract context
    maintainer_guidance = _get_maintainer_guidance(
        trusted_comments,
        config["trusted_sources"]["maintainers"],
    )
    coderabbit_plan = _get_coderabbit_plan(
        trusted_comments,
        config["extraction_patterns"]["coderabbit"],
    )
    ai_triage = _get_ai_triage_info(
        trusted_comments,
        config["extraction_patterns"]["ai_triage"]["marker"],
    )

    has_content = _has_synthesizable_content(maintainer_guidance, coderabbit_plan, ai_triage)
    existing_synthesis = _find_existing_synthesis(comments, config["synthesis"]["marker"])

    # Dry-run mode
    if args.dry_run:
        if has_content:
            synthesis_body = _build_synthesis_comment(
                config["synthesis"]["marker"],
                maintainer_guidance,
                coderabbit_plan,
                ai_triage,
            )
            print("\n=== SYNTHESIS PREVIEW ===")
            print(synthesis_body)
            print("=== END PREVIEW ===")
            if existing_synthesis:
                print(f"\nWould UPDATE existing comment (ID: {existing_synthesis['id']})")
            else:
                print("\nWould CREATE new synthesis comment")
        else:
            print("\nNo synthesizable content found, would SKIP synthesis comment")
        print(f"Would ASSIGN copilot-swe-agent to issue #{issue_number}")
        return 0

    # Post or update synthesis
    response = None
    action = "Skipped"

    if has_content:
        synthesis_body = _build_synthesis_comment(
            config["synthesis"]["marker"],
            maintainer_guidance,
            coderabbit_plan,
            ai_triage,
        )

        if existing_synthesis:
            print(f"Updating existing synthesis comment (ID: {existing_synthesis['id']})")
            response = update_issue_comment(owner, repo, existing_synthesis["id"], synthesis_body)
            action = "Updated"
        else:
            print("Creating new synthesis comment")
            response = create_issue_comment(owner, repo, issue_number, synthesis_body)
            action = "Created"
        print(f"{action} synthesis comment: {response.get('html_url', 'N/A')}")
    else:
        print("No synthesizable content found, skipping synthesis comment")

    # Assign Copilot
    assigned = False
    if not args.skip_assignment:
        print("Assigning copilot-swe-agent...")
        assigned = _assign_copilot(owner, repo, issue_number)
        if assigned:
            print(f"Assigned copilot-swe-agent to issue #{issue_number}")
    else:
        print("Skipping assignment (handled by workflow with COPILOT_GITHUB_TOKEN)")

    output = {
        "success": True,
        "action": action,
        "issue_number": issue_number,
        "comment_id": response["id"] if response else None,
        "comment_url": response.get("html_url") if response else None,
        "assigned": assigned,
        "marker": config["synthesis"]["marker"],
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
