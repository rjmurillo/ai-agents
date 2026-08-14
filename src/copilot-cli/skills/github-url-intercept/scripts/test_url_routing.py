#!/usr/bin/env python3
"""Parse GitHub URLs and route to efficient API calls.

Parses a GitHub URL and returns the recommended command to fetch its
content via API instead of HTML. Routes to github skill scripts when
available, falls back to gh api for other resource types.

Supported URL types:
- Gists: gist.github.com/{owner}/{id}
- Pull requests: /pull/{n}, /pull/{n}#discussion_r{id}
- Issues: /issues/{n}, /issues/{n}#issuecomment-{id}
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
import shlex
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class UrlType(StrEnum):
    GIST = "Gist"
    PULL = "Pull"
    ISSUE = "Issue"
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

# ---------------------------------------------------------------------------
# Input validation patterns (CWE-78 mitigation)
# ---------------------------------------------------------------------------

SAFE_OWNER_REPO_RE = re.compile(r"^[a-zA-Z0-9][-a-zA-Z0-9_.]*$")
SAFE_REF_RE = re.compile(r"^[a-zA-Z0-9][-a-zA-Z0-9_./]*$")
SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9][-a-zA-Z0-9_./%+@]*$")
SAFE_GIST_ID_RE = re.compile(r"(?:[0-9]+|[a-fA-F0-9]{20}|[a-fA-F0-9]{32})")
SAFE_GIST_REVISION_RE = re.compile(r"[a-fA-F0-9]{40}")
DANGEROUS_CHARS = set("\"'`$;&|><(){}[]!\\")
GIST_SUFFIXES = {"revisions"}
GIST_HOSTS = {"gist.github.com", "gist.githubusercontent.com"}


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

    return bool(pattern.fullmatch(value))


def is_safe_raw_path(segments: list[str]) -> bool:
    """Reject path forms that gh or the remote server could reinterpret."""
    for segment in segments:
        decoded = unquote(segment)
        if decoded in {".", ".."}:
            return False
        if any(ord(character) < 32 or ord(character) == 127 for character in decoded):
            return False
        if any(character in DANGEROUS_CHARS for character in decoded):
            return False
        if "/" in decoded or "\\" in decoded:
            return False
    return True


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------


def parse_gist_url(url: str) -> dict[str, Any] | None:
    """Parse a gist URL and discard suffixes that do not affect API routing."""
    if any(ord(character) < 32 or ord(character) == 127 for character in url):
        return None

    try:
        parsed_url = urlsplit(url)
    except ValueError:
        return None

    if parsed_url.scheme not in {"http", "https"}:
        return None
    if parsed_url.netloc not in GIST_HOSTS:
        return None

    segments = [segment for segment in parsed_url.path.split("/") if segment]
    if not segments:
        return None

    raw_content_url = parsed_url.netloc == "gist.githubusercontent.com"
    ownerless_with_suffix = (
        len(segments) > 1
        and is_safe_input(segments[0], SAFE_GIST_ID_RE)
        and (
            segments[1] in GIST_SUFFIXES
            or is_safe_input(segments[1], SAFE_GIST_REVISION_RE)
        )
    )
    if raw_content_url:
        if len(segments) < 2:
            return None
        if len(segments) < 3 or segments[2] != "raw":
            return None
        owner = segments[0]
        gist_id = segments[1]
        selector_segments = segments[2:]
    elif len(segments) == 1 or ownerless_with_suffix:
        owner = None
        gist_id = segments[0]
        selector_segments = segments[1:]
    else:
        owner = segments[0]
        gist_id = segments[1]
        selector_segments = segments[2:]

    embed_url = gist_id.endswith(".js")
    gist_id = gist_id.removesuffix(".js")
    if owner is not None and not is_safe_input(owner, SAFE_OWNER_REPO_RE):
        return None
    if not is_safe_input(gist_id, SAFE_GIST_ID_RE):
        return None

    raw_request = raw_content_url or (
        bool(selector_segments) and selector_segments[0] == "raw"
    )
    raw_url = None
    revision = None
    requested_file = None
    requested_file_slug = None
    requested_file_base_slug = None
    if raw_request:
        if parsed_url.query or parsed_url.fragment:
            return None
        raw_selectors = selector_segments[1:]
        if not is_safe_raw_path(raw_selectors):
            return None
        raw_url = urlunsplit(
            (
                "https",
                parsed_url.netloc,
                parsed_url.path,
                parsed_url.query,
                "",
            )
        )
    elif selector_segments:
        selector = selector_segments[0]
        if selector == "revisions":
            selector_segments = selector_segments[1:]
        elif is_safe_input(selector, SAFE_GIST_REVISION_RE):
            revision = selector
            selector_segments = selector_segments[1:]
        else:
            return None
        if selector_segments:
            return None

    if not raw_request:
        if embed_url:
            query_files = parse_qs(
                parsed_url.query,
                keep_blank_values=True,
            ).get("file", [])
            if len(query_files) > 1 or (query_files and not query_files[0]):
                return None
            if query_files:
                requested_file = query_files[0]
        if requested_file is None and parsed_url.fragment.startswith("file-"):
            requested_file_slug = unquote(parsed_url.fragment.removeprefix("file-"))
            requested_file_base_slug = re.sub(
                r"-L\d+(?:-L\d+)?$",
                "",
                requested_file_slug,
            )

    return {
        "owner": owner,
        "repo": None,
        "url_type": UrlType.GIST.value,
        "resource_id": gist_id,
        "raw_url": raw_url,
        "revision": revision,
        "requested_file": requested_file,
        "requested_file_slug": requested_file_slug,
        "requested_file_base_slug": requested_file_base_slug,
        "ref": None,
        "path": None,
        "fragment_type": None,
        "fragment_id": None,
    }


def parse_github_url(url: str) -> dict[str, Any] | None:
    """Parse a GitHub URL into structured components.

    Returns None if the URL is invalid or contains dangerous characters.
    """
    gist = parse_gist_url(url)
    if gist is not None:
        return gist

    match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)/?(.*)$", url)
    if not match:
        return None

    owner = match.group(1)
    repo = match.group(2)
    rest = match.group(3)

    # Validate owner and repo (CWE-78)
    if not is_safe_input(owner, SAFE_OWNER_REPO_RE):
        return None
    if not is_safe_input(repo, SAFE_OWNER_REPO_RE):
        return None

    # Check for fragments
    fragment_type = None
    fragment_id = None

    review_match = re.search(r"#pullrequestreview-(\d+)", url)
    discussion_match = re.search(r"#discussion_r(\d+)", url)
    comment_match = re.search(r"#issuecomment-(\d+)", url)

    if review_match:
        fragment_type = "pullrequestreview"
        fragment_id = review_match.group(1)
        rest = rest.split("#")[0]
    elif discussion_match:
        fragment_type = "discussion_r"
        fragment_id = discussion_match.group(1)
        rest = rest.split("#")[0]
    elif comment_match:
        fragment_type = "issuecomment"
        fragment_id = comment_match.group(1)
        rest = rest.split("#")[0]

    # Parse resource type
    url_type = UrlType.UNKNOWN
    resource_id = None
    ref = None
    path = None

    pull_match = re.match(r"^pull/(\d+)", rest)
    issue_match = re.match(r"^issues/(\d+)", rest)
    blob_match = re.match(r"^blob/([^/]+)/(.+)$", rest)
    tree_match = re.match(r"^tree/([^/]+)/(.*)$", rest)
    commit_match = re.match(r"^commit/([a-f0-9]+)", rest)
    compare_match = re.match(r"^compare/(.+)$", rest)

    if pull_match:
        url_type = UrlType.PULL
        resource_id = pull_match.group(1)
    elif issue_match:
        url_type = UrlType.ISSUE
        resource_id = issue_match.group(1)
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

    return {
        "owner": owner,
        "repo": repo,
        "url_type": url_type.value,
        "resource_id": resource_id,
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

    # Use scripts for PRs and issues (primary)
    if url_type_enum in SCRIPT_ROUTES:
        route = SCRIPT_ROUTES[url_type_enum]
        resource_id = parsed["resource_id"]

        cmd_map = {
            UrlType.PULL: (
                f'python3 "{route["path"]}" --pull-request "{resource_id}"'
                f' --owner "{owner}" --repo "{repo}"'
            ),
            UrlType.ISSUE: (
                f'python3 "{route["path"]}" --issue "{resource_id}"'
                f' --owner "{owner}" --repo "{repo}"'
            ),
        }

        return {
            "method": RouteMethod.SCRIPT.value,
            "command": cmd_map.get(url_type_enum, "unknown"),
            "script_path": route["path"],
            "reason": "Use github skill script for structured output",
        }

    # Fallback to gh api
    ref = parsed["ref"]
    path = parsed["path"]
    resource_id = parsed["resource_id"]

    raw_url = parsed.get("raw_url")
    gist_revision = parsed.get("revision")
    if raw_url:
        gist_command = f"gh api {shlex.quote(raw_url)}"
    else:
        gist_endpoint = f"gists/{resource_id}"
        if gist_revision:
            gist_endpoint = f"{gist_endpoint}/{gist_revision}"
        gist_command = f'gh api "{gist_endpoint}"'

    requested_file = parsed.get("requested_file")
    if requested_file:
        jq_query = f".files[{json.dumps(requested_file)}]"
        gist_command = f"{gist_command} --jq {shlex.quote(jq_query)}"
    requested_file_slug = parsed.get("requested_file_slug")
    if requested_file_slug:
        slug = json.dumps(requested_file_slug.lower())
        base_slug = json.dumps(parsed.get("requested_file_base_slug", "").lower())
        selected_slug = base_slug if base_slug != slug else slug
        jq_query = (
            'def slug: ascii_downcase | gsub("[^a-z0-9_-]+"; "-") '
            '| sub("^-+"; "") | sub("-+$"; ""); '
            ".files | to_entries | "
            f'map(select((.key | slug) == {selected_slug})) | '
            'if length == 1 then .[0].value else error("ambiguous or missing file selector") end'
        )
        gist_command = f"{gist_command} --jq {shlex.quote(jq_query)}"

    fallback_map: dict[UrlType, str] = {
        UrlType.GIST: gist_command,
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
