#!/usr/bin/env python3
"""Audit closing claims across open pull requests.

Paginates open PRs and extracts closing keywords (Fixes, Closes, Resolves,
etc.) from the PR body. Classifies each claim by Markdown context and resolves
the target issue state when GitHub exposes it.

Markdown context classification:
  active         - plain prose, closes the referenced issue on merge
  code_span      - inside backtick(s), does not close
  fenced_code    - inside triple-backtick or triple-tilde block
  html_comment   - inside <!-- ... -->
  escaped_hash   - hash escaped with backslash (\\#NNN), does not close
  negated        - phrase like "does not close #NNN" or "won't fix #NNN"

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
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+"
    r"(?:(?P<owner>[a-zA-Z0-9_.-]+)/(?P<repo2>[a-zA-Z0-9_.-]+))?(?P<escape>\\?)#(?P<number>\d+)",
    re.IGNORECASE,
)

# Negation phrases that precede the keyword.
_NEGATION_RE = re.compile(
    r"\b(?:does\s+not|won'?t|will\s+not|doesn'?t|not)\s+",
    re.IGNORECASE,
)

_PRS_QUERY = """\
query($owner: String!, $repo: String!, $cursor: String) {
    repository(owner: $owner, name: $repo) {
        pullRequests(states: [OPEN], first: 50, after: $cursor,
                     orderBy: {field: CREATED_AT, direction: DESC}) {
            pageInfo { hasNextPage endCursor }
            nodes {
                number
                title
                baseRefName
                body
                closingIssuesReferences(first: 10) {
                    nodes { number state }
                }
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
    i = 0
    while i < len(text):
        if not in_fence:
            m = re.match(r"^(`{3,}|~{3,})", text[i:])
            if m:
                fence_char = m.group(1)[0]
                fence_len = len(m.group(1))
                in_fence = True
                # Mark the fence opener
                for j in range(i, min(i + fence_len, len(text))):
                    fenced_positions.add(j)
                i += fence_len
                # Skip rest of the opening line
                while i < len(text) and text[i] != "\n":
                    fenced_positions.add(i)
                    i += 1
            else:
                i += 1
        else:
            # Look for closing fence
            m = re.match(rf"^{re.escape(fence_char)}{{3,}}", text[i:])
            if m:
                fence_len = len(m.group(0))
                for j in range(i, min(i + fence_len, len(text))):
                    fenced_positions.add(j)
                i += fence_len
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
    for m in re.finditer(r"<!--.*?-->", text, re.DOTALL):
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

    # Check for inline code span (single backtick).
    before = text[:start]
    backtick_count = before.count("`") - before.count("``")
    if backtick_count % 2 == 1:
        return "code_span"

    # Check for negation immediately before the keyword.
    preceding = text[max(0, start - 30):start]
    if _NEGATION_RE.search(preceding):
        return "negated"

    return "active"


def _resolve_closing_refs(
    pr_closing_nodes: list[dict[str, Any]],
) -> dict[int, str]:
    """Build a map from issue number to state from GraphQL closingIssuesReferences."""
    result: dict[int, str] = {}
    for node in pr_closing_nodes:
        num = node.get("number")
        state = node.get("state", "")
        if num is not None:
            result[int(num)] = state
    return result


def extract_claims(
    pr_number: int,
    body: str,
    base_branch: str,
    closing_refs: dict[int, str],
    owner: str,
    repo: str,
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

        target_state = closing_refs.get(target_num, "unknown")

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
                and target_owner == owner
                and target_repo_name == repo
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

        prs_data = (data.get("repository") or {}).get("pullRequests") or {}
        nodes.extend(prs_data.get("nodes") or [])
        page_info = prs_data.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break

    return nodes


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Audit closing claims in open PRs.")
    p.add_argument("--owner", default="")
    p.add_argument("--repo", default="")
    p.add_argument("--state", default="open", choices=["open"],
                   help="PR state to audit (only 'open' supported)")
    p.add_argument("--artifact", default="",
                   help="Optional path to write JSON evidence artifact")
    p.add_argument("--resume-from", type=int, default=0,
                   help="Skip PRs with number <= this value (for resuming)")
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
        if args.resume_from and pr_num <= args.resume_from:
            continue

        body = node.get("body") or ""
        base_branch = node.get("baseRefName") or ""
        closing_nodes = (node.get("closingIssuesReferences") or {}).get("nodes") or []
        closing_refs = _resolve_closing_refs(closing_nodes)

        claims = extract_claims(pr_num, body, base_branch, closing_refs, owner, repo)
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
            write_skill_error(
                f"Failed to write artifact: {exc}", 3, error_type="IOError",
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
