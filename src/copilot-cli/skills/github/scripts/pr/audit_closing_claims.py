#!/usr/bin/env python3
"""Audit closing claims across open pull requests.

Paginates open PRs and extracts closing keywords (Fixes, Closes, Resolves,
etc.) from three sources: the PR body, every commit message on the PR, and
any auto-merge headline/body override. Classifies each claim by Markdown
context (body only) and resolves the target issue state when GitHub exposes
it. The classification and extraction logic lives in the sibling module
`closing_claim_extraction.py` (see its docstring); this file owns GraphQL
and REST fetching, CLI parsing, and output.

Markdown context classification (body claims only):
  active         - plain prose, closes when the PR targets the default branch
  code_span      - inside backtick(s), does not close
  fenced_code    - inside triple-backtick or triple-tilde block
  html_comment   - inside <!-- ... -->
  escaped_hash   - hash escaped with backslash (\\#NNN), does not close

Commit-message and auto-merge-override context classification:
  active         - plain text, reaches the squash commit if that source is live
  escaped_hash   - hash escaped with backslash (\\#NNN), does not close

Commit messages and auto-merge overrides are not Markdown: GitHub's merge UI
and API render them as plain text, so the body-only code_span/fenced_code/
html_comment classes do not apply there. This narrower classifier is a
deliberate divergence from the body classifier, not an oversight.

Reachability: whether a commit-message or auto-merge-override claim can end
up as text in the eventual squash commit (and therefore close its target on
merge) depends on:
  - the repository's `squash_merge_commit_message` setting (REST field, see
    `repos/{owner}/{repo}` -> `squash_merge_commit_message`; confirmed live
    values via `gh api repos/rjmurillo/ai-agents --jq .squash_merge_commit_message`
    during Issue #4462 triage). "COMMIT_MESSAGES" and
    "PR_BODY_AND_COMMIT_DETAILS" fold every commit message into the squash
    commit text; "PR_BODY" and "BLANK" do not.
  - a per-PR auto-merge commit-message override
    (`autoMergeRequest.commitHeadline` / `commitBody` in the GraphQL schema).
    When either is set, that text replaces the repository default for that
    PR's eventual squash commit, so commit messages no longer reach it
    independently; the override text itself does.

A commit or auto-merge claim is "unsupported" when it is classified "active",
reaches the squash commit under the rule above, and targets an issue that no
"active" body claim already covers with `github_will_close: true`. An
unsupported reachable claim means the squash merge can close an issue nobody
reviewing the PR description would expect, which is the exact failure mode
Issue #4462 measured across 27 PR/issue pairs before the repository setting
was changed to PR_BODY. `main()` refuses to report a clean audit when one is
found: it still writes the full evidence (including any `--artifact`) but
returns exit code 1 instead of 0.

Exit codes follow ADR-035:
    0 - Audit complete, no unsupported reachable claim found
    1 - Audit complete, but an unsupported claim can reach the squash commit
    2 - Not found / empty fleet / local --artifact write failure
    3 - API error
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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
_script_dir = os.path.dirname(__file__)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

# CLOSING_KEYWORDS_RE, _strip_fenced_code, _strip_html_comments,
# classify_claim, and classify_commit_claim are re-exported here (unused in
# this file's own code, hence noqa: F401) so tests and other callers can
# keep reaching them as attributes of this module, unchanged from before
# the closing_claim_extraction.py split.
from closing_claim_extraction import (
    CLOSING_KEYWORDS_RE as _CLOSING_KEYWORDS_RE,  # noqa: F401
)
from closing_claim_extraction import (
    COMMIT_REACHING_SQUASH_SETTINGS as _COMMIT_REACHING_SQUASH_SETTINGS,
)
from closing_claim_extraction import (
    _strip_fenced_code,  # noqa: F401
    _strip_html_comments,  # noqa: F401
    classify_claim,  # noqa: F401
    classify_commit_claim,  # noqa: F401
    extract_claims,
    extract_reachable_claims,
)
from closing_claim_extraction import (
    mark_unsupported_claims as _mark_unsupported_claims,
)
from closing_claim_extraction import (
    resolve_closing_refs as _resolve_closing_refs,
)
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
                autoMergeRequest {
                    commitHeadline
                    commitBody
                }
                commits(first: 100) {
                    pageInfo { hasNextPage endCursor }
                    nodes { commit { message } }
                }
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

_COMMITS_QUERY = """\
query($owner: String!, $repo: String!, $number: Int!, $cursor: String!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            commits(first: 100, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes { commit { message } }
            }
        }
    }
}"""


def fetch_repo_squash_setting(owner: str, repo: str) -> str:
    """Return the repository's `squash_merge_commit_message` REST setting.

    Raises RuntimeError on any `gh api` failure so callers can map it to the
    same exit-3 (API error) handling used for GraphQL failures.
    """
    result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}", "--jq", ".squash_merge_commit_message"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or f"gh api repos/{owner}/{repo} failed with no stderr or stdout output"
        )
    value = result.stdout.strip()
    return value or "PR_BODY"


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
            _complete_commits(owner, repo, node)
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


def _complete_commits(
    owner: str,
    repo: str,
    pr_node: dict[str, Any],
) -> None:
    """Fetch every commit on one PR node (message text only)."""
    connection = pr_node.get("commits") or {}
    page_info = connection.get("pageInfo") or {}

    while page_info.get("hasNextPage"):
        cursor = page_info.get("endCursor")
        if not cursor:
            raise RuntimeError(f"PR #{pr_node.get('number', 0)} commits omitted a cursor")
        variables = {
            "owner": owner,
            "repo": repo,
            "number": int(pr_node.get("number") or 0),
            "cursor": cursor,
        }
        data = gh_graphql(_COMMITS_QUERY, variables)
        pull_request = (data.get("repository") or {}).get("pullRequest") or {}
        next_connection = pull_request.get("commits") or {}
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


def _collect_pr_claims(
    node: dict[str, Any],
    owner: str,
    repo: str,
    squash_setting: str,
) -> list[dict[str, Any]]:
    """Return every claim (body, commit, auto-merge override) for one PR node."""
    pr_num = node.get("number") or 0
    body = node.get("body") or ""
    base_branch = node.get("baseRefName") or ""
    default_branch = node.get("defaultBranchName") or ""
    closing_nodes = (node.get("closingIssuesReferences") or {}).get("nodes") or []
    closing_refs = _resolve_closing_refs(closing_nodes)

    claims = extract_claims(
        pr_num, body, base_branch, closing_refs, owner, repo, default_branch,
    )

    auto_merge = node.get("autoMergeRequest") or {}
    override_text = "\n".join(
        part for part in (auto_merge.get("commitHeadline"), auto_merge.get("commitBody")) if part
    )
    has_override = bool(override_text.strip())

    commit_nodes = (node.get("commits") or {}).get("nodes") or []
    commit_text = "\n".join(
        (n.get("commit") or {}).get("message", "") for n in commit_nodes
    )

    # An auto-merge commit-message override replaces the repository's
    # default squash text for this PR entirely, so plain commit messages no
    # longer reach the squash commit independently; the override text does.
    commit_reaches = (not has_override) and squash_setting in _COMMIT_REACHING_SQUASH_SETTINGS
    claims.extend(
        extract_reachable_claims(
            pr_num, commit_text, "commit", commit_reaches, closing_refs, owner, repo,
        )
    )
    claims.extend(
        extract_reachable_claims(
            pr_num, override_text, "auto_merge_override", has_override, closing_refs, owner, repo,
        )
    )

    _mark_unsupported_claims(claims)
    return claims


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    try:
        squash_setting = fetch_repo_squash_setting(owner, repo)
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        write_skill_error(
            str(exc), 3, error_type="ApiError",
            output_format=fmt, script_name=_SCRIPT_NAME,
        )
        return 3

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

        all_claims.extend(_collect_pr_claims(node, owner, repo, squash_setting))
        audited_prs += 1

    unsupported_claims = [c for c in all_claims if c["unsupported"]]

    result = {
        "Success": True,
        "Owner": owner,
        "Repo": repo,
        "RepoSquashMergeMessageSetting": squash_setting,
        "AuditedPRs": audited_prs,
        "TotalClaims": len(all_claims),
        "UnsupportedReachableClaims": len(unsupported_claims),
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
            #
            # Exit code 2, not 3: ADR-035 reserves 3 for an external
            # service/API error, and this OSError comes from a local
            # filesystem write (--artifact), never from the network or the
            # GitHub API. A missing parent directory, a full disk, or a
            # permissions error is the "usage, configuration, or
            # environment error" category ADR-035 assigns to exit code 2
            # (Copilot review on PR #5283, following the ADR-035
            # exit-code contract this module's header already cites).
            write_skill_error(
                f"Failed to write artifact: {exc}", 2, error_type="General",
                output_format=fmt, script_name=_SCRIPT_NAME,
            )
            return 2

    if unsupported_claims:
        write_skill_output(
            result,
            output_format=fmt,
            human_summary=(
                f"Audited {audited_prs} open PR(s): {len(unsupported_claims)} unsupported "
                "claim(s) can reach the squash commit"
            ),
            status="FAIL",
            script_name=_SCRIPT_NAME,
        )
        return 1

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
