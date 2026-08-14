
#!/usr/bin/env python3
"""Parse GitHub URLs and route to efficient API calls.

Parses a GitHub URL and returns the recommended command to fetch its
content via API instead of HTML. Routes to github skill scripts when
available, falls back to gh api for other resource types.

Supported URL types:
- Gists: gist.github.com/{owner}/{id}
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
import sys
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# Path-based callers do not add the script directory. Bootstrap it before
# sibling imports so canonical and generated copies load outside package context.
from gist_routing import build_gist_command, parse_gist_url  # noqa: E402
from url_validation import (  # noqa: E402
    SAFE_OWNER_REPO_RE,
    SAFE_PATH_RE,
    SAFE_REF_RE,
    is_safe_input,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class UrlType(StrEnum):
    GIST = "Gist"
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
# URL parsing
# ---------------------------------------------------------------------------


FRAGMENT_PATTERNS = (
    ("pullrequestreview", re.compile(r"pullrequestreview-(\d+)$")),
    ("discussion_r", re.compile(r"(?:discussion_r|r)(\d+)$")),
    ("issuecomment", re.compile(r"issuecomment-(\d+)$")),
)


def _parse_fragment(fragment: str, rest: str) -> tuple[str, str | None, str | None]:
    if not fragment:
        return rest, None, None

    for fragment_type, pattern in FRAGMENT_PATTERNS:
        match = pattern.fullmatch(fragment)
        if match:
            return rest, fragment_type, match.group(1)
    return "", None, None


def _parse_blob(
    match: re.Match[str],
) -> tuple[UrlType, str | None, str | None, str | None, str | None] | None:
    ref, path = match.groups()
    if not is_safe_input(ref, SAFE_REF_RE):
        return None
    if not is_safe_input(path, SAFE_PATH_RE):
        return None
    return UrlType.BLOB, None, None, None, ref, path


def _parse_tree(
    match: re.Match[str],
) -> tuple[UrlType, str | None, str | None, str | None, str | None] | None:
    ref, path = match.groups()
    if not is_safe_input(ref, SAFE_REF_RE):
        return None
    if path and not is_safe_input(path, SAFE_PATH_RE, allow_empty=True):
        return None
    return UrlType.TREE, None, None, None, ref, path


def _parse_resource(
    rest: str,
) -> tuple[UrlType, str | None, str | None, str | None, str | None] | None:
    pull_match = re.fullmatch(r"pull/(\d+)(?:/(checks|files|changes|commits))?", rest)
    if pull_match:
        return UrlType.PULL, pull_match.group(1), pull_match.group(2), None, None, None

    issue_match = re.fullmatch(r"issues/(\d+)", rest)
    if issue_match:
        return UrlType.ISSUE, issue_match.group(1), None, None, None, None

    discussion_match = re.fullmatch(r"discussions/(\d+)", rest)
    if discussion_match:
        return UrlType.DISCUSSION, discussion_match.group(1), None, None, None, None

    actions_match = re.fullmatch(r"actions/runs/(\d+)(?:/job/(\d+))?", rest)
    if actions_match:
        job_id = actions_match.group(2)
        if job_id:
            return UrlType.ACTIONS, job_id, "job", actions_match.group(1), None, None
        return UrlType.ACTIONS, actions_match.group(1), None, None, None, None

    blob_match = re.fullmatch(r"blob/([^/]+)/(.+)", rest)
    if blob_match:
        return _parse_blob(blob_match)

    tree_match = re.fullmatch(r"tree/([^/]+)/(.*)", rest)
    if tree_match:
        return _parse_tree(tree_match)

    commit_match = re.fullmatch(r"commit/([a-fA-F0-9]{7,40})", rest)
    if commit_match:
        return UrlType.COMMIT, commit_match.group(1), None, None, None, None

    compare_match = re.fullmatch(r"compare/(.+)", rest)
    if compare_match:
        resource_id = compare_match.group(1)
        if not is_safe_input(resource_id, SAFE_REF_RE, allow_triple_dot=True):
            return None
        return UrlType.COMPARE, resource_id, None, None, None, None

    return None


def parse_github_url(url: str) -> dict[str, Any] | None:
    """Parse a GitHub URL into structured components.

    Returns None if the URL is invalid or contains dangerous characters.
    """
    gist = parse_gist_url(url)
    if gist is not None:
        return gist

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

    rest, fragment_type, fragment_id = _parse_fragment(split.fragment, rest)
    resource = _parse_resource(rest)
    if resource is None:
        return None
    url_type, resource_id, subroute, secondary_id, ref, path = resource

    return {
        "owner": owner,
        "repo": repo,
        "url_type": url_type.value,
        "resource_id": resource_id,
        "subroute": subroute,
        "secondary_id": secondary_id,
        "ref": ref,
        "path": path,
        "fragment_type": fragment_type,
        "fragment_id": fragment_id,
    }


# ---------------------------------------------------------------------------
# Route recommendation
# ---------------------------------------------------------------------------


def get_recommended_route(parsed: dict[str, Any]) -> dict[str, Any]:
    """Determine the optimal command for a parsed GitHub URL."""
    owner = parsed["owner"]
    repo = parsed["repo"]

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
        subroute = parsed.get("subroute")

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
        UrlType.GIST: build_gist_command(parsed),
        UrlType.DISCUSSION: (
            f'gh api "repos/{owner}/{repo}/discussions/{resource_id}"'
        ),
        UrlType.ACTIONS: (
            f'gh api "repos/{owner}/{repo}/actions/jobs/{resource_id}"'
            if parsed.get("secondary_id")
            else f'gh api "repos/{owner}/{repo}/actions/runs/{resource_id}"'
        ),
        UrlType.BLOB: f'gh api "repos/{owner}/{repo}/contents/{path}?ref={ref}"',
        UrlType.TREE: f'gh api "repos/{owner}/{repo}/contents/{path}?ref={ref}"',
        UrlType.COMMIT: f'gh api "repos/{owner}/{repo}/commits/{resource_id}"',
        UrlType.COMPARE: f'gh api "repos/{owner}/{repo}/compare/{resource_id}"',
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
