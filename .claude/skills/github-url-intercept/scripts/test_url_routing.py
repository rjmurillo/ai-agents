#!/usr/bin/env python3
"""Parse GitHub URLs and route to efficient API calls.

Parses a GitHub URL and returns the recommended command to fetch its
content via API instead of HTML. Routes to github skill scripts when
available, falls back to gh api for other resource types.

Supported URL types:
- Pull requests: /pull/{n}, /pull/{n}/checks, /pull/{n}/files,
  /pull/{n}/changes, /pull/{n}/commits
- Issues: /issues/{n}
- Discussions: /discussions/{n}
- Actions: /actions/runs/{run_id}, /actions/runs/{run_id}/job/{job_id}
- Files: /blob/{ref}/{path}, /tree/{ref}/{path}
- Commits: /commit/{sha}
- Comparisons: /compare/{base}...{head}

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid URL format
"""

from __future__ import annotations

import argparse
import json
import re
from enum import StrEnum
from urllib.parse import urlsplit
from typing import Any

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class UrlType(StrEnum):
    PULL = "Pull"
    ISSUE = "Issue"
    DISCUSSION = "Discussion"
    ACTIONS = "Actions"
    BLOB = "Blob"
    TREE = "Tree"
    COMMIT = "Commit"
    COMPARE = "Compare"
    UNKNOWN = "Unknown"


class RouteMethod(StrEnum):
    SCRIPT = "Script"
    GH_API = "GhApi"


# ---------------------------------------------------------------------------
# Script routes (primary routing)
# ---------------------------------------------------------------------------

SCRIPT_ROUTES: dict[UrlType, dict[str, str]] = {
    UrlType.PULL: {
        "script": "get_pr_context.py",
        "path": ".claude/skills/github/scripts/pr/get_pr_context.py",
    },
    UrlType.ISSUE: {
        "script": "get_issue_context.py",
        "path": ".claude/skills/github/scripts/issue/get_issue_context.py",
    },
}

CHECKS_SCRIPT_PATH = ".claude/skills/github/scripts/pr/get_pr_checks.py"

# ---------------------------------------------------------------------------
# Input validation patterns (CWE-78 mitigation)
# ---------------------------------------------------------------------------

SAFE_OWNER_REPO_RE = re.compile(r"^[a-zA-Z0-9][-a-zA-Z0-9_.]*$")
SAFE_REF_RE = re.compile(r"^[a-zA-Z0-9][-a-zA-Z0-9_./]*$")
SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9][-a-zA-Z0-9_./%+@]*$")
DANGEROUS_CHARS = set("\"'`$;&|><(){}[]!\\")


def is_safe_input(
    value: str | None,
    pattern: re.Pattern[str],
    allow_empty: bool = False,
    allow_triple_dot: bool = False,
) -> bool:
    """Validate input against command injection attacks."""
    if not value:
        return allow_empty

    # Check for dangerous characters
    if any(ch in DANGEROUS_CHARS for ch in value):
        return False

    # Check for path traversal
    if allow_triple_dot:
        test_value = value.replace("...", "__TRIPLE__")
        if ".." in test_value:
            return False
    elif ".." in value:
        return False

    return bool(pattern.match(value))


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------


def parse_github_url(url: str) -> dict | None:
    """Parse a GitHub URL into structured components.

    Returns None if the URL is invalid or contains dangerous characters.
    """
    split = urlsplit(url)
    if split.scheme not in {"http", "https"} or split.netloc != "github.com":
        return None

    path_parts = split.path.split("/", 3)
    if len(path_parts) < 3 or path_parts[0] != "":
        return None

    owner = path_parts[1]
    repo = path_parts[2]
    rest = path_parts[3] if len(path_parts) == 4 else ""

    # Validate owner and repo (CWE-78)
    if not is_safe_input(owner, SAFE_OWNER_REPO_RE):
        return None
    if not is_safe_input(repo, SAFE_OWNER_REPO_RE):
        return None

    # Check for fragments. Unsupported fragments are rejected rather than
    # ignored so the validator does not accept a route shape it does not
    # understand.
    fragment_type = None
    fragment_id = None

    fragment = split.fragment
    if fragment:
        review_match = re.fullmatch(r"pullrequestreview-(\d+)", fragment)
        discussion_match = re.fullmatch(r"(?:discussion_r|r)(\d+)", fragment)
        comment_match = re.fullmatch(r"issuecomment-(\d+)", fragment)

        if review_match:
            fragment_type = "pullrequestreview"
            fragment_id = review_match.group(1)
        elif discussion_match:
            fragment_type = "discussion_r"
            fragment_id = discussion_match.group(1)
        elif comment_match:
            fragment_type = "issuecomment"
            fragment_id = comment_match.group(1)
        else:
            return None

    # Parse resource type
    url_type = UrlType.UNKNOWN
    resource_id = None
    secondary_id = None
    subroute = None
    ref = None
    path = None

    pull_match = re.fullmatch(r"pull/(\d+)(?:/(checks|files|changes|commits))?", rest)
    issue_match = re.fullmatch(r"issues/(\d+)", rest)
    discussion_match = re.fullmatch(r"discussions/(\d+)", rest)
    actions_match = re.fullmatch(r"actions/runs/(\d+)(?:/job/(\d+))?", rest)
    blob_match = re.fullmatch(r"blob/([^/]+)/(.+)", rest)
    tree_match = re.fullmatch(r"tree/([^/]+)/(.+)", rest)
    commit_match = re.fullmatch(r"commit/([a-fA-F0-9]{7,40})", rest)
    compare_match = re.fullmatch(r"compare/(.+)", rest)

    if pull_match:
        url_type = UrlType.PULL
        resource_id = pull_match.group(1)
        subroute = pull_match.group(2)
    elif issue_match:
        url_type = UrlType.ISSUE
        resource_id = issue_match.group(1)
    elif discussion_match:
        url_type = UrlType.DISCUSSION
        resource_id = discussion_match.group(1)
    elif actions_match:
        url_type = UrlType.ACTIONS
        job_id = actions_match.group(2)
        if job_id:
            resource_id = job_id
            secondary_id = actions_match.group(1)
            subroute = "job"
        else:
            resource_id = actions_match.group(1)
    elif blob_match:
        url_type = UrlType.BLOB
        ref = blob_match.group(1)
        path = blob_match.group(2)
        if not is_safe_input(ref, SAFE_REF_RE):
            return None
        if not is_safe_input(path, SAFE_PATH_RE):
            return None
    elif tree_match:
        url_type = UrlType.TREE
        ref = tree_match.group(1)
        path = tree_match.group(2)
        if not is_safe_input(ref, SAFE_REF_RE):
            return None
        if path and not is_safe_input(path, SAFE_PATH_RE, allow_empty=True):
            return None
    elif commit_match:
        url_type = UrlType.COMMIT
        resource_id = commit_match.group(1)
    elif compare_match:
        url_type = UrlType.COMPARE
        resource_id = compare_match.group(1)
        if not is_safe_input(resource_id, SAFE_REF_RE, allow_triple_dot=True):
            return None

    if url_type == UrlType.UNKNOWN:
        return None

    return {
        "owner": owner,
        "repo": repo,
        "url_type": url_type.value,
        "resource_id": resource_id,
        "secondary_id": secondary_id,
        "subroute": subroute,
        "ref": ref,
        "path": path,
        "fragment_type": fragment_type,
        "fragment_id": fragment_id,
    }


# ---------------------------------------------------------------------------
# Route recommendation
# ---------------------------------------------------------------------------


def get_recommended_route(parsed: dict) -> dict:
    """Determine the optimal command for a parsed GitHub URL."""
    owner = parsed["owner"]
    repo = parsed["repo"]
    subroute = parsed.get("subroute")

    # Fragments require direct API call
    if parsed["fragment_type"] and parsed["fragment_id"]:
        frag_type = parsed["fragment_type"]
        frag_id = parsed["fragment_id"]
        resource_id = parsed["resource_id"]

        cmd_map = {
            "pullrequestreview": (
                f'gh api "repos/{owner}/{repo}/pulls/{resource_id}'
                f'/reviews/{frag_id}"'
            ),
            "discussion_r": (
                f'gh api "repos/{owner}/{repo}/pulls/comments/{frag_id}"'
            ),
            "issuecomment": (
                f'gh api "repos/{owner}/{repo}/issues/comments/{frag_id}"'
            ),
        }

        cmd = cmd_map.get(frag_type, "unknown")
        return {
            "method": RouteMethod.GH_API.value,
            "command": cmd,
            "script_path": None,
            "reason": f"Fragment {frag_type} requires direct API call",
        }

    url_type_enum = UrlType(parsed["url_type"])

    if url_type_enum == UrlType.PULL:
        route = SCRIPT_ROUTES[UrlType.PULL]
        resource_id = parsed["resource_id"]
        if subroute == "checks":
            return {
                "method": RouteMethod.SCRIPT.value,
                "command": (
                    f'python3 "{CHECKS_SCRIPT_PATH}" --pull-request "{resource_id}"'
                ),
                "script_path": CHECKS_SCRIPT_PATH,
                "reason": "Use github skill script for structured output",
            }

        extra_flag = {
            "files": " --include-changed-files",
            "changes": " --include-diff",
            "commits": "",
            None: "",
        }.get(subroute, None)
        if extra_flag is None:
            return {
                "method": RouteMethod.GH_API.value,
                "command": "unknown",
                "script_path": None,
                "reason": f"No routing available for URL type: {parsed['url_type']}",
            }
        return {
            "method": RouteMethod.SCRIPT.value,
            "command": (
                f'python3 "{route["path"]}" --pull-request "{resource_id}"'
                f' --owner "{owner}" --repo "{repo}"{extra_flag}'
            ),
            "script_path": route["path"],
            "reason": "Use github skill script for structured output",
        }

    if url_type_enum == UrlType.ISSUE:
        route = SCRIPT_ROUTES[UrlType.ISSUE]
        resource_id = parsed["resource_id"]
        return {
            "method": RouteMethod.SCRIPT.value,
            "command": (
                f'python3 "{route["path"]}" --issue "{resource_id}"'
                f' --owner "{owner}" --repo "{repo}"'
            ),
            "script_path": route["path"],
            "reason": "Use github skill script for structured output",
        }

    # Fallback to gh api
    ref = parsed["ref"]
    path = parsed["path"]
    resource_id = parsed["resource_id"]

    fallback_map: dict[UrlType, str] = {
        UrlType.BLOB: f'gh api "repos/{owner}/{repo}/contents/{path}?ref={ref}"',
        UrlType.TREE: f'gh api "repos/{owner}/{repo}/contents/{path}?ref={ref}"',
        UrlType.COMMIT: f'gh api "repos/{owner}/{repo}/commits/{resource_id}"',
        UrlType.COMPARE: f'gh api "repos/{owner}/{repo}/compare/{resource_id}"',
        UrlType.DISCUSSION: (
            f'gh api "repos/{owner}/{repo}/discussions/{resource_id}"'
        ),
    }

    if url_type_enum == UrlType.ACTIONS:
        cmd = (
            f'gh api "repos/{owner}/{repo}/actions/jobs/{parsed["resource_id"]}"'
            if parsed.get("secondary_id")
            else f'gh api "repos/{owner}/{repo}/actions/runs/{resource_id}"'
        )
        return {
            "method": RouteMethod.GH_API.value,
            "command": cmd,
            "script_path": None,
            "reason": "No script available for Actions, use gh api",
        }

    cmd = fallback_map.get(url_type_enum, "unknown")
    return {
        "method": RouteMethod.GH_API.value,
        "command": cmd,
        "script_path": None,
        "reason": f"No script available for {parsed['url_type']}, use gh api",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse a GitHub URL and return routing recommendation.",
    )
    parser.add_argument(
        "--url", required=True, help="The GitHub URL to route",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    parsed = parse_github_url(args.url)

    if parsed is None:
        output: dict[str, Any] = {
            "success": False,
            "parsed_url": None,
            "recommended_route": None,
            "error": "Invalid GitHub URL format",
        }
        print(json.dumps(output, indent=2))
        return 1

    recommended = get_recommended_route(parsed)

    if recommended["command"] == "unknown":
        output = {
            "success": False,
            "parsed_url": parsed,
            "recommended_route": None,
            "error": f"No routing available for URL type: {parsed['url_type']}",
        }
        print(json.dumps(output, indent=2))
        return 1

    output = {
        "success": True,
        "parsed_url": parsed,
        "recommended_route": recommended,
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
