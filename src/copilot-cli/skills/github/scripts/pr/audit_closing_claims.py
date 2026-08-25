#!/usr/bin/env python3
"""Audit closing claims across open pull requests.

Paginates open PRs and extracts closing keywords (Fixes, Closes, Resolves,
etc.) from the PR body. Classifies each claim by Markdown context and resolves
the target issue state when GitHub exposes it.

Markdown context classification:
  active         - plain prose, closes when the PR targets the default branch
  code_span      - inside backtick(s), does not close
  fenced_code    - inside triple-backtick or triple-tilde block
  html_comment   - inside <!-- ... -->
  escaped_hash   - hash escaped with backslash (\\#NNN), does not close

Exit codes follow ADR-035:
    0 - Audit complete
    2 - Not found / empty fleet
    3 - API error
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    gh_graphql,
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

_SCRIPT_NAME = "audit_closing_claims.py"

# GitHub's recognised closing keywords (case-insensitive).
_CLOSING_KEYWORDS_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)(?::)?\s+"
    r"(?:(?P<owner>[a-zA-Z0-9_.-]+)/(?P<repo2>[a-zA-Z0-9_.-]+))?(?P<escape>\\?)#(?P<number>\d+)",
    re.IGNORECASE,
)

_PRS_QUERY = """\
query($owner: String!, $repo: String!, $cursor: String) {
    repository(owner: $owner, name: $repo) {
        defaultBranchRef { name }
        pullRequests(states: [OPEN], first: 50, after: $cursor,
                     orderBy: {field: CREATED_AT, direction: DESC}) {
            pageInfo { hasNextPage endCursor }
            nodes {
                number
                title
                baseRefName
                body
                closingIssuesReferences(first: 100) {
                    pageInfo { hasNextPage endCursor }
                    nodes { number state repository { nameWithOwner } }
                }
            }
        }
    }
}"""

_CLOSING_REFS_QUERY = """\
query($owner: String!, $repo: String!, $number: Int!, $cursor: String!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            closingIssuesReferences(first: 100, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes { number state repository { nameWithOwner } }
            }
        }
    }
}"""


def _strip_fenced_code(text: str) -> tuple[str, set[int]]:
    """Return (text_with_fenced_replaced, set_of_positions_in_fenced_blocks).

    Replaces fenced code block content with spaces to neutralise keyword
    matches within them. Returns the original text positions that are inside
    fenced code.
    """
    fenced_positions: set[int] = set()
    result = list(text)
    in_fence = False
    fence_char = ""
    opening_fence_length = 0
    i = 0
    while i < len(text):
        if not in_fence:
            is_line_start = i == 0 or text[i - 1] == "\n"
            m = re.match(r" {0,3}(`{3,}|~{3,})", text[i:]) if is_line_start else None
            if m:
                fence = m.group(1)
                fence_char = fence[0]
                opening_fence_length = len(fence)
                in_fence = True
                # Mark the fence opener
                for j in range(i, min(i + len(m.group(0)), len(text))):
                    fenced_positions.add(j)
                i += len(m.group(0))
                # Skip rest of the opening line
                while i < len(text) and text[i] != "\n":
                    fenced_positions.add(i)
                    i += 1
            else:
                i += 1
        else:
            # Look for closing fence
            is_line_start = i == 0 or text[i - 1] == "\n"
            m = (
                re.match(
                    rf" {{0,3}}{re.escape(fence_char)}"
                    rf"{{{opening_fence_length},}}(?=[ \t]*(?:\n|\Z))",
                    text[i:],
                )
                if is_line_start
                else None
            )
            if m:
                for j in range(i, min(i + len(m.group(0)), len(text))):
                    fenced_positions.add(j)
                i += len(m.group(0))
                in_fence = False
            else:
                fenced_positions.add(i)
                i += 1
    # Replace fenced positions with space in result
    for pos in fenced_positions:
        result[pos] = " "
    return "".join(result), fenced_positions


def _strip_html_comments(text: str) -> tuple[str, set[int]]:
    """Return (text_with_html_comments_replaced, set_of_comment_positions)."""
    comment_positions: set[int] = set()
    result = list(text)
    for m in re.finditer(r"<!--.*?(?:-->|\Z)", text, re.DOTALL):
        for i in range(m.start(), m.end()):
            comment_positions.add(i)
            result[i] = " "
    return "".join(result), comment_positions


def classify_claim(
    text: str,
    match: re.Match[str],
    fenced_positions: set[int],
    html_comment_positions: set[int],
) -> str:
    """Return the Markdown context classification for a keyword match."""
    start = match.start()

    if start in fenced_positions:
        return "fenced_code"

    if start in html_comment_positions:
        return "html_comment"

    # Check for escaped hash: \#NNN
    hash_pos = match.start() + match.group(0).index("#")
    if hash_pos > 0 and text[hash_pos - 1] == "\\":
        return "escaped_hash"

    if _inside_code_span(text, start):
        return "code_span"

    return "active"


def _inside_code_span(text: str, position: int) -> bool:
    """Return whether position is inside a paired backtick code span."""
    openers: dict[int, re.Match[str]] = {}
    for run in re.finditer(r"`+", text):
        delimiter_length = len(run.group(0))
        opener = openers.pop(delimiter_length, None)
        if opener is None:
            openers[delimiter_length] = run
            continue
        if opener.end() <= position < run.start():
            return True
    return False


def _resolve_closing_refs(
    pr_closing_nodes: list[dict[str, Any]],
) -> dict[tuple[str, str, int], str]:
    """Build an owner, repository, and issue state map from closing references."""
    result: dict[tuple[str, str, int], str] = {}
    for node in pr_closing_nodes:
        num = node.get("number")
        state = node.get("state", "")
        name_with_owner = (node.get("repository") or {}).get("nameWithOwner", "")
        if num is not None and "/" in name_with_owner:
            target_owner, target_repo = name_with_owner.split("/", 1)
            result[(target_owner.casefold(), target_repo.casefold(), int(num))] = state
    return result


def extract_claims(
    pr_number: int,
    body: str,
    base_branch: str,
    closing_refs: dict[tuple[str, str, int], str],
    owner: str,
    repo: str,
    default_branch: str = "main",
) -> list[dict[str, Any]]:
    """Parse closing claims from one PR body."""
    if not body:
        return []

    _, fenced_positions = _strip_fenced_code(body)
    _, html_positions = _strip_html_comments(body)

    claims: list[dict[str, Any]] = []
    for m in _CLOSING_KEYWORDS_RE.finditer(body):
        target_num = int(m.group("number"))
        context_cls = classify_claim(body, m, fenced_positions, html_positions)
        target_owner = m.group("owner") or owner
        target_repo_name = m.group("repo2") or repo
        target_key = (
            target_owner.casefold(),
            target_repo_name.casefold(),
            target_num,
        )

        target_state = closing_refs.get(target_key, "unknown")

        claims.append({
            "pr_number": pr_number,
            "claim_text": m.group(0),
            "target_number": target_num,
            "target_owner": target_owner,
            "target_repo": target_repo_name,
            "target_state": target_state,
            "base_branch": base_branch,
            "context_class": context_cls,
            "github_will_close": (
                context_cls == "active"
                and base_branch == default_branch
                and target_key in closing_refs
            ),
        })
    return claims


def fetch_open_prs(owner: str, repo: str) -> list[dict[str, Any]]:
    """Paginate all open PRs and return raw node list."""
    nodes: list[dict[str, Any]] = []
    cursor: str | None = None

    for _ in range(200):  # safety cap: 200 pages * 50 = 10,000 PRs
        variables: dict[str, Any] = {"owner": owner, "repo": repo}
        if cursor:
            variables["cursor"] = cursor
        try:
            data = gh_graphql(_PRS_QUERY, variables)
        except RuntimeError as exc:
            raise RuntimeError(f"GraphQL query failed: {exc}") from exc

        repository = data.get("repository") or {}
        default_branch = (repository.get("defaultBranchRef") or {}).get("name")
        if not default_branch:
            raise RuntimeError("GraphQL response omitted repository default branch")
        prs_data = repository.get("pullRequests") or {}
        page_nodes = prs_data.get("nodes") or []
        for node in page_nodes:
            node["defaultBranchName"] = default_branch
            _complete_closing_references(owner, repo, node)
        nodes.extend(page_nodes)
        page_info = prs_data.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break

    return nodes


def _complete_closing_references(
    owner: str,
    repo: str,
    pr_node: dict[str, Any],
) -> None:
    """Fetch every closing issue reference for one PR node."""
    connection = pr_node.get("closingIssuesReferences") or {}
    page_info = connection.get("pageInfo") or {}

    while page_info.get("hasNextPage"):
        cursor = page_info.get("endCursor")
        if not cursor:
            raise RuntimeError(
                f"PR #{pr_node.get('number', 0)} closing references omitted a cursor"
            )
        variables = {
            "owner": owner,
            "repo": repo,
            "number": int(pr_node.get("number") or 0),
            "cursor": cursor,
        }
        data = gh_graphql(_CLOSING_REFS_QUERY, variables)
        pull_request = (data.get("repository") or {}).get("pullRequest") or {}
        next_connection = pull_request.get("closingIssuesReferences") or {}
        connection.setdefault("nodes", []).extend(next_connection.get("nodes") or [])
        page_info = next_connection.get("pageInfo") or {}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Audit closing claims in open PRs.")
    p.add_argument("--owner", default="")
    p.add_argument("--repo", default="")
    p.add_argument("--state", default="open", choices=["open"],
                   help="PR state to audit (only 'open' supported)")
    p.add_argument("--artifact", default="",
                   help="Optional path to write JSON evidence artifact")
    p.add_argument("--resume-from", type=int, default=0,
                   help="Skip PRs with number >= this value (for resuming)")
    add_output_format_arg(p)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    try:
        pr_nodes = fetch_open_prs(owner, repo)
    except RuntimeError as exc:
        write_skill_error(
            str(exc), 3, error_type="ApiError",
            output_format=fmt, script_name=_SCRIPT_NAME,
        )
        return 3

    if not pr_nodes:
        write_skill_error(
            "No open PRs found", 2, error_type="NotFound",
            output_format=fmt, script_name=_SCRIPT_NAME,
        )
        return 2

    all_claims: list[dict[str, Any]] = []
    audited_prs = 0

    for node in pr_nodes:
        pr_num = node.get("number") or 0
        if args.resume_from and pr_num >= args.resume_from:
            continue

        body = node.get("body") or ""
        base_branch = node.get("baseRefName") or ""
        default_branch = node.get("defaultBranchName") or ""
        closing_nodes = (node.get("closingIssuesReferences") or {}).get("nodes") or []
        closing_refs = _resolve_closing_refs(closing_nodes)

        claims = extract_claims(
            pr_num,
            body,
            base_branch,
            closing_refs,
            owner,
            repo,
            default_branch,
        )
        all_claims.extend(claims)
        audited_prs += 1

    result = {
        "Success": True,
        "Owner": owner,
        "Repo": repo,
        "AuditedPRs": audited_prs,
        "TotalClaims": len(all_claims),
        "Claims": all_claims,
    }

    if args.artifact:
        try:
            with open(args.artifact, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
        except OSError as exc:
            # "IOError" is not in VALID_ERROR_TYPES (ADR-103): the enum
            # covers API/HTTP-shaped error categories, and no filesystem
            # category exists or is warranted for one caller. Mapped to
            # "General", the documented catch-all, rather than widening the
            # enum. Before this fix, write_skill_error raised ValueError on
            # this exact call, turning a handled OSError into an unhandled
            # crash (Copilot review on PR #5283).
            write_skill_error(
                f"Failed to write artifact: {exc}", 3, error_type="General",
                output_format=fmt, script_name=_SCRIPT_NAME,
            )
            return 3

    write_skill_output(
        result,
        output_format=fmt,
        human_summary=(
            f"Audited {audited_prs} open PR(s), found {len(all_claims)} closing claim(s)"
        ),
        status="PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
