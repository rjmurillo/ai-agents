"""GitHub API helpers: auth, pagination, GraphQL, issue comments, rate limits."""

from __future__ import annotations

import enum
import json
import logging
import re
import subprocess
import sys
import time
import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:
    from scripts.github_core.protocol import GitHubClient

from scripts.github_core.validation import is_github_name_valid

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level helpers (log sanitation, thread predicates)
# ---------------------------------------------------------------------------


def safe_log_str(value: object) -> str:
    """Strip CR/LF from a value before logging it.

    Defends against CWE-117 log forging: GraphQL error messages and other
    remote-sourced text that flow into ``error=%s`` placeholders may contain
    embedded `\\r\\n` sequences that, unsanitized, allow an attacker to
    forge a fake log line. Keeping the substitution in one named helper
    means future log-injection risk is closed at one site, not 12.
    """
    return str(value).replace("\r", "\\r").replace("\n", "\\n")


def count_unresolved_threads(thread_nodes: list[dict]) -> int:
    """Count threads whose ``isResolved`` is False.

    Single authoritative definition of "unresolved" (DRY): the merge-ready
    inline-page filter and the paginated-helper post-filter MUST share this
    rule. If the rule changes (e.g., treating an outdated thread differently),
    one edit propagates everywhere. The default for missing ``isResolved`` is
    True so a malformed thread does not silently count as unresolved.
    """
    return sum(1 for t in thread_nodes if not t.get("isResolved", True))


def filter_unresolved_threads(thread_nodes: list[dict]) -> list[dict]:
    """Return only threads whose ``isResolved`` is False. See
    ``count_unresolved_threads`` for the canonical definition.
    """
    return [t for t in thread_nodes if not t.get("isResolved", True)]


def transform_review_thread(thread: dict, include_comments: bool = False) -> dict:
    """Transform a raw GraphQL review-thread node into the canonical flat shape.

    Single authoritative definition (DRY) of the review-thread output shape
    shared by ``get_pr_review_threads.py`` and
    ``get_unresolved_review_threads.py``. A consumer that reads one script's
    ``threads`` list can read the other's without a shape branch, which is the
    bug this consolidates: the lighter unresolved script previously emitted raw
    GraphQL nodes (``{"id", "isResolved", "comments": {"nodes": [...]}}``) while
    the richer script emitted this flat shape, so ``thread["comments"][-1]``
    crashed against one and worked against the other.

    ``include_comments`` controls whether the full comment list is materialized.
    When False (the cheap-probe default), ``comments`` is None and only the
    ``first_comment_*`` fields are populated; the caller still pays for one
    comment per thread in its GraphQL query, never the whole conversation.
    """
    comments_nodes = thread.get("comments", {}).get("nodes", [])
    first = comments_nodes[0] if comments_nodes else None

    result: dict = {
        "thread_id": thread.get("id"),
        "is_resolved": thread.get("isResolved", False),
        "is_outdated": thread.get("isOutdated", False),
        "path": thread.get("path"),
        "line": thread.get("line"),
        "start_line": thread.get("startLine"),
        "diff_side": thread.get("diffSide"),
        "comment_count": thread.get("comments", {}).get("totalCount", 0),
        "first_comment_id": first.get("databaseId") if first else None,
        "first_comment_author": (
            first.get("author", {}).get("login") if first and first.get("author") else None
        ),
        "first_comment_body": first.get("body") if first else None,
        "first_comment_created_at": first.get("createdAt") if first else None,
        "comments": None,
    }

    if include_comments:
        result["comments"] = [
            {
                "id": c.get("databaseId"),
                "author": c.get("author", {}).get("login") if c.get("author") else None,
                "body": c.get("body"),
                "created_at": c.get("createdAt"),
            }
            for c in comments_nodes
        ]

    return result


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepoInfo:
    """Repository owner and name.

    Replaces raw ``dict[str, str]`` returns that had inconsistent key
    casing across modules.  Attribute access (``info.owner``) is enforced
    by the type checker, eliminating ``KeyError`` risks.
    """

    owner: str
    repo: str


@dataclass
class RateLimitResult:
    """Structured result from rate limit check."""

    success: bool
    resources: dict[str, dict]
    summary_markdown: str
    core_remaining: int


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def error_and_exit(message: str, exit_code: int) -> NoReturn:
    """Write an error to stderr and exit with the given code.

    Exit codes follow ADR-035:
        0 - Success
        1 - Invalid parameters / logic error
        2 - Config error
        3 - External error (API failure)
        4 - Auth error (not authenticated, permission denied)
    """
    print(message, file=sys.stderr)
    raise SystemExit(exit_code)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

_GITHUB_REMOTE_PATTERN = re.compile(r"github\.com[:/]([^/]+)/([^/.]+)")


def get_repo_info() -> RepoInfo | None:
    """Infer repository owner and name from git remote origin URL.

    Returns:
        RepoInfo with owner and repo, or None if not in a git repo.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None

        match = _GITHUB_REMOTE_PATTERN.search(result.stdout.strip())
        if match:
            return RepoInfo(
                owner=match.group(1),
                repo=re.sub(r"\.git$", "", match.group(2)),
            )
    except subprocess.TimeoutExpired:
        logger.debug("git remote get-url origin timed out")
    except FileNotFoundError:
        logger.debug("git executable not found on PATH")
    return None


def resolve_repo_params(owner: str = "", repo: str = "") -> RepoInfo:
    """Resolve owner and repo, inferring from git remote if not provided.

    Raises SystemExit if parameters cannot be determined or are invalid.

    Returns:
        RepoInfo with owner and repo.
    """
    if not owner or not repo:
        repo_info = get_repo_info()
        if repo_info:
            owner = owner or repo_info.owner
            repo = repo or repo_info.repo
        else:
            error_and_exit(
                "Could not infer repository info. Please provide -Owner and -Repo parameters.",
                2,
            )

    if not is_github_name_valid(owner, "Owner"):
        error_and_exit(f"Invalid GitHub owner name: {owner}", 2)
    if not is_github_name_valid(repo, "Repo"):
        error_and_exit(f"Invalid GitHub repository name: {repo}", 2)

    return RepoInfo(owner=owner, repo=repo)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def is_gh_authenticated() -> bool:
    """Check if GitHub CLI is installed and authenticated."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except FileNotFoundError:
        logger.debug("GitHub CLI (gh) not found on PATH")
        return False
    except subprocess.TimeoutExpired:
        logger.debug("gh auth status timed out")
        return False


def assert_gh_authenticated() -> None:
    """Ensure GitHub CLI is authenticated. Raises SystemExit if not."""
    if not is_gh_authenticated():
        error_and_exit(
            "GitHub CLI (gh) is not installed or not authenticated. Run 'gh auth login' first.",
            4,
        )


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def gh_api_paginated(endpoint: str, page_size: int = 100) -> list[dict]:
    """Fetch all pages from a GitHub REST API endpoint.

    Args:
        endpoint: API path (e.g. "repos/owner/repo/pulls/1/comments").
        page_size: Items per page (1-100, default 100).

    Returns:
        Combined list of items across all pages.
    """
    all_items: list[dict] = []
    page = 1

    while True:
        separator = "&" if "?" in endpoint else "?"
        url = f"{endpoint}{separator}per_page={page_size}&page={page}"

        result = subprocess.run(
            ["gh", "api", url],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            msg = (
                f"GitHub API request failed for endpoint '{endpoint}' "
                f"(page {page}): {result.stderr}"
            )
            if page == 1:
                error_and_exit(msg, 3)
            else:
                warnings.warn(
                    f"{msg}. Returning partial results from {len(all_items)} items.",
                    stacklevel=2,
                )
                break

        try:
            items = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            msg = f"Invalid JSON from endpoint '{endpoint}' (page {page}): {exc}"
            if page == 1:
                error_and_exit(msg, 3)
            else:
                warnings.warn(
                    f"{msg}. Returning {len(all_items)} partial results.",
                    stacklevel=2,
                )
                break
        if not items:
            break

        all_items.extend(items)
        if len(items) < page_size:
            break

        page += 1

    return all_items


def gh_graphql(query: str, variables: dict | None = None) -> dict:
    """Execute a GitHub GraphQL query or mutation.

    Uses GraphQL variables for safe parameterization (ADR-015 compliant).

    Args:
        query: The GraphQL query string.
        variables: Dict of variables. Strings use -f, ints/bools use -F.

    Returns:
        The 'data' portion of the GraphQL response.

    Raises:
        RuntimeError: On GraphQL transport or response errors.
    """
    if variables is None:
        variables = {}

    gh_args = ["gh", "api", "graphql", "-f", f"query={query}"]

    for key, value in variables.items():
        if isinstance(value, (int, bool)):
            gh_args.extend(["-F", f"{key}={value}"])
        else:
            gh_args.extend(["-f", f"{key}={value}"])

    result = subprocess.run(
        gh_args,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        msg_match = re.search(r'"message"\s*:\s*"([^"]+)"', error_msg)
        if msg_match:
            error_msg = msg_match.group(1)
        raise RuntimeError(f"GraphQL request failed: {error_msg}")

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse GraphQL response: {result.stdout}") from exc

    if parsed.get("errors"):
        messages = [e.get("message", str(e)) for e in parsed["errors"]]
        raise RuntimeError(f"GraphQL errors: {'; '.join(messages)}")

    data: dict = parsed.get("data", {})
    return data


def get_all_prs_with_comments(
    owner: str,
    repo: str,
    since: datetime,
    max_pages: int = 50,
) -> list[dict]:
    """Fetch PRs with review comments using GraphQL cursor-based pagination.

    PRs are ordered by updatedAt DESC; pagination stops when PRs fall
    outside the requested time range.

    Args:
        owner: Repository owner.
        repo: Repository name.
        since: Only include PRs updated since this datetime.
        max_pages: Safety limit (default 50, yielding up to 2500 PRs).

    Returns:
        List of PR dicts that have review comments within the time range.
    """
    query = """\
query($owner: String!, $repo: String!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequests(first: 50, orderBy: {field: UPDATED_AT, direction: DESC}, after: $cursor) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        number
        title
        state
        author { login }
        createdAt
        updatedAt
        mergedAt
        closedAt
        reviewThreads(first: 100) {
          nodes {
            isResolved
            isOutdated
            comments(first: 50) {
              nodes {
                id
                body
                author { login }
                createdAt
                path
              }
            }
          }
        }
      }
    }
  }
}"""

    all_prs: list[dict] = []
    cursor: str | None = None
    has_next_page = True
    page_count = 0

    while has_next_page and page_count < max_pages:
        page_count += 1

        variables: dict = {"owner": owner, "repo": repo}
        if cursor:
            variables["cursor"] = cursor

        data = gh_graphql(query, variables)

        repo_data = data.get("repository")
        if repo_data is None:
            raise RuntimeError(
                f"Repository {owner}/{repo} not found or not accessible"
            )
        pr_data = repo_data.get("pullRequests")
        if pr_data is None:
            raise RuntimeError(
                f"Could not retrieve pull requests for {owner}/{repo}"
            )

        for pr in pr_data["nodes"]:
            updated_at = datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))
            if updated_at < since:
                has_next_page = False
                break

            threads = pr.get("reviewThreads", {}).get("nodes", [])
            has_comments = any(
                len(t.get("comments", {}).get("nodes", [])) > 0 for t in threads
            )
            if has_comments:
                all_prs.append(pr)

        if has_next_page:
            has_next_page = pr_data["pageInfo"]["hasNextPage"]
            cursor = pr_data["pageInfo"]["endCursor"]

        logger.debug("Page %d processed, total PRs with comments: %d", page_count, len(all_prs))

    if page_count >= max_pages:
        warnings.warn(f"Reached maximum page limit ({max_pages})", stacklevel=2)

    return all_prs


# ---------------------------------------------------------------------------
# Issue comments
# ---------------------------------------------------------------------------

# Regex for detecting 403 permission errors (negative lookarounds prevent
# false positives on IDs like "Comment ID 4030").
_403_PATTERN = re.compile(
    r"((?<!\d)403(?!\d)|\bforbidden\b|Resource not accessible by integration)",
    re.IGNORECASE,
)

_403_GUIDANCE = """\
PERMISSION DENIED (403): Cannot update comment {comment_id} in {owner}/{repo}.

LIKELY CAUSES:
- GitHub Apps: Missing "issues": "write" permission in app manifest
- Workflow GITHUB_TOKEN: Add 'permissions: issues: write' to workflow YAML
- Fine-grained PAT: Enable 'Issues' repository permission (Read and Write)
- Classic PAT: Requires 'repo' scope for private repos or 'public_repo' for public repos
- Not the comment author: Only the comment author or repo admin can edit comments

RAW ERROR: {error}"""


def get_issue_comments(
    owner: str,
    repo: str,
    issue_number: int,
    client: GitHubClient | None = None,
) -> list[dict]:
    """Fetch all comments for a GitHub issue.

    When *client* is provided, delegates to ``client.rest_get``.
    Otherwise falls back to the existing paginated ``gh api`` subprocess call.
    """
    if client is not None:
        endpoint = f"repos/{owner}/{repo}/issues/{issue_number}/comments"
        result = client.rest_get(endpoint)
        return result if isinstance(result, list) else [result]
    return gh_api_paginated(f"repos/{owner}/{repo}/issues/{issue_number}/comments")


def update_issue_comment(owner: str, repo: str, comment_id: int, body: str) -> dict:
    """Update an existing GitHub issue comment.

    Raises SystemExit with code 4 for permission errors, code 3 for other API errors.
    """
    payload = json.dumps({"body": body})

    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/issues/comments/{comment_id}",
            "-X", "PATCH",
            "--input", "-",
        ],
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        if _403_PATTERN.search(error_str):
            guidance = _403_GUIDANCE.format(
                comment_id=comment_id,
                owner=owner,
                repo=repo,
                error=error_str,
            )
            error_and_exit(guidance, 4)
        error_and_exit(f"Failed to update comment: {error_str}", 3)

    try:
        response: dict = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Comment {comment_id} may have been updated but response was not valid JSON: "
            f"{result.stdout!r}"
        ) from exc
    return response


def create_issue_comment(
    owner: str,
    repo: str,
    issue_number: int,
    body: str,
    client: GitHubClient | None = None,
) -> dict:
    """Create a new GitHub issue comment.

    When *client* is provided, delegates to ``client.rest_post``.
    Otherwise falls back to the existing ``gh api`` subprocess call.

    Raises SystemExit with code 3 on API failure (subprocess path only).
    """
    endpoint = f"repos/{owner}/{repo}/issues/{issue_number}/comments"

    if client is not None:
        return client.rest_post(endpoint, {"body": body})

    payload = json.dumps({"body": body})

    result = subprocess.run(
        ["gh", "api", endpoint, "-X", "POST", "--input", "-"],
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        error_and_exit(f"Failed to post comment: {error_str}", 3)

    try:
        response: dict = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Comment creation succeeded but response was not valid JSON: {result.stdout!r}"
        ) from exc
    return response


# ---------------------------------------------------------------------------
# Trusted sources
# ---------------------------------------------------------------------------


def get_trusted_source_comments(
    comments: list[dict],
    trusted_users: list[str],
) -> list[dict]:
    """Filter comments to those from trusted source users.

    Args:
        comments: List of comment dicts with nested user.login.
        trusted_users: Usernames to keep.

    Returns:
        Filtered list of comments from trusted users.
    """
    if not comments:
        return []
    return [c for c in comments if c.get("user", {}).get("login") in trusted_users]


# ---------------------------------------------------------------------------
# PR review threads
# ---------------------------------------------------------------------------


# Safety bound on the reviewThreads pagination loop. A PR with >5000 threads
# is almost certainly a misuse rather than a real review state; we exit
# rather than spin forever. The PR #1887 retrospective records that the
# prior single-page first:100 query masked 6+ unresolved threads twice.
_REVIEW_THREADS_MAX_PAGES = 50

_REVIEW_THREADS_QUERY = """\
query($owner: String!, $name: String!, $prNumber: Int!, $cursor: String) {
    repository(owner: $owner, name: $name) {
        pullRequest(number: $prNumber) {
            reviewThreads(first: 100, after: $cursor) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    isResolved
                    comments(first: 1) {
                        nodes {
                            databaseId
                        }
                    }
                }
            }
        }
    }
}"""


class FetchStatus(enum.StrEnum):
    """Result classification for one reviewThreads page fetch.

    The caller distinguishes ``TRANSPORT_ERROR`` (return [] to preserve the
    never-raises contract) from ``STRUCTURAL_MISSING`` (break the loop with
    whatever was collected). ``OK`` means a usable page is returned.
    Using StrEnum instead of bare strings keeps the type checker honest
    and makes a typo (``FetchStatus.OK_`` vs ``FetchStatus.OK``) a fail-
    fast attribute error rather than a silent miss.
    """

    OK = "ok"
    TRANSPORT_ERROR = "transport_error"
    STRUCTURAL_MISSING = "structural_missing"


def _fetch_review_threads_page(
    owner: str,
    repo: str,
    pull_request: int,
    cursor: str | None,
    pages_seen: int,
    aggregated_count: int,
) -> tuple[FetchStatus, dict | None]:
    """Fetch one page of reviewThreads.

    Returns ``(status, review_threads_dict)``. status is one of
    ``FetchStatus.OK`` / ``FetchStatus.TRANSPORT_ERROR`` / ``FetchStatus.STRUCTURAL_MISSING``.
    Each failure branch logs a distinct ``op=review_threads_failed
    reason=...`` line so the surface is greppable.
    """
    variables: dict = {"owner": owner, "name": repo, "prNumber": pull_request}
    if cursor is not None:
        variables["cursor"] = cursor

    try:
        data = gh_graphql(_REVIEW_THREADS_QUERY, variables)
    except RuntimeError as exc:
        logger.warning(
            "op=review_threads_failed pr=%d owner=%s repo=%s "
            "page=%d aggregated=%d reason=graphql_error error=%s",
            pull_request, owner, repo, pages_seen, aggregated_count,
            safe_log_str(exc),
        )
        warnings.warn(
            f"Failed to query review threads for PR #{pull_request} "
            f"on page {pages_seen} (collected {aggregated_count} so far): {exc}",
            stacklevel=2,
        )
        return FetchStatus.TRANSPORT_ERROR, None

    repository = data.get("repository") or {}
    pull_request_obj = repository.get("pullRequest")
    if pull_request_obj is None:
        logger.warning(
            "op=review_threads_failed pr=%d owner=%s repo=%s "
            "page=%d aggregated=%d reason=pr_not_found",
            pull_request, owner, repo, pages_seen, aggregated_count,
        )
        return FetchStatus.STRUCTURAL_MISSING, None
    review_threads = pull_request_obj.get("reviewThreads")
    if review_threads is None:
        logger.warning(
            "op=review_threads_failed pr=%d owner=%s repo=%s "
            "page=%d aggregated=%d reason=field_missing",
            pull_request, owner, repo, pages_seen, aggregated_count,
        )
        return FetchStatus.STRUCTURAL_MISSING, None
    if review_threads.get("nodes") is None:
        # Aligns with the taxonomy in
        # .claude/skills/github/scripts/pr/get_pr_review_threads.py:
        # `nodes_missing` is a distinct GraphQL response shape from
        # `field_missing` (the connection itself is present but its node
        # list is null). Operators grepping by reason find both surfaces.
        logger.warning(
            "op=review_threads_failed pr=%d owner=%s repo=%s "
            "page=%d aggregated=%d reason=nodes_missing",
            pull_request, owner, repo, pages_seen, aggregated_count,
        )
        return FetchStatus.STRUCTURAL_MISSING, None

    return FetchStatus.OK, review_threads


def _log_review_threads_page(
    pull_request: int, pages_seen: int, cursor: str | None,
    page_info: dict, page_nodes: list, aggregated_count: int,
) -> None:
    """Per-page DEBUG log; full cursor so adjacent pages with shared 8-char
    prefixes can be distinguished.
    """
    logger.debug(
        "op=review_threads_page pr=%d page=%d cursor_in=%s end_cursor=%s "
        "nodes=%d cumulative=%d has_next=%s",
        pull_request, pages_seen,
        cursor if cursor else "<start>",
        page_info.get("endCursor"),
        len(page_nodes), aggregated_count,
        bool(page_info.get("hasNextPage")),
    )


def _warn_review_threads_capped(pull_request: int, aggregated_count: int) -> None:
    """Emit cap-truncation warning. The PR #1887 retro names silent
    truncation as the false-zero failure class; the warning is the
    machine-readable signal that the result is a lower bound, not exact.
    """
    warnings.warn(
        f"Hit _REVIEW_THREADS_MAX_PAGES={_REVIEW_THREADS_MAX_PAGES} for "
        f"PR #{pull_request}; result truncated at {aggregated_count} "
        f"threads. Unresolved-thread count is a lower bound, not exact.",
        stacklevel=3,
    )


def get_unresolved_review_threads(
    owner: str,
    repo: str,
    pull_request: int,
) -> list[dict]:
    """Retrieve unresolved review threads on a pull request.

    Pages through reviewThreads until ``pageInfo.hasNextPage`` is false or
    ``_REVIEW_THREADS_MAX_PAGES`` is reached. Returns ``[]`` on transport
    failure (never raises, never partial). On a cap-hit, returns whatever
    was collected and emits ``warnings.warn``. The PR #1887 retrospective
    records that the prior single-page first:100 query hid 6+ unresolved
    threads; this loop plus the cap-warn close both silent-truncation
    failure modes.
    """
    op_start = time.monotonic()
    aggregated: list[dict] = []
    cursor: str | None = None
    pages_seen = 0

    while pages_seen < _REVIEW_THREADS_MAX_PAGES:
        pages_seen += 1
        status, review_threads = _fetch_review_threads_page(
            owner, repo, pull_request, cursor, pages_seen, len(aggregated),
        )
        if status == FetchStatus.TRANSPORT_ERROR:
            return []
        if status == FetchStatus.STRUCTURAL_MISSING:
            if pages_seen > 1:
                # Mid-pagination structural failure: pages 1..N-1 succeeded
                # and page N returned a structurally invalid response. The
                # callers see a truncated result, so emit the same surfaced
                # warning shape used for cursor_missing and page-cap-exceeded
                # rather than letting the empty-page silently terminate the
                # loop. Page 1 failures already return [] above; the guard
                # here is the multi-page case.
                warnings.warn(
                    f"Mid-pagination structural failure for PR "
                    f"#{pull_request} on page {pages_seen}; result truncated "
                    f"at {len(aggregated)} threads. Reason: structural_failure.",
                    stacklevel=2,
                )
                logger.warning(
                    "op=review_threads_failed pr=%d owner=%s repo=%s "
                    "page=%d aggregated=%d reason=structural_failure",
                    pull_request, owner, repo, pages_seen, len(aggregated),
                )
            break
        assert review_threads is not None  # noqa: S101
        page_nodes = review_threads.get("nodes", [])
        aggregated.extend(page_nodes)

        page_info = review_threads.get("pageInfo") or {}
        _log_review_threads_page(
            pull_request, pages_seen, cursor, page_info,
            page_nodes, len(aggregated),
        )
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            # hasNextPage was true but endCursor is empty/null. Cannot
            # advance — surface as a truncation event rather than a clean
            # exit, since callers would otherwise see a "complete"-looking
            # result that silently dropped pages 2+.
            warnings.warn(
                f"hasNextPage=true but endCursor empty for PR "
                f"#{pull_request} on page {pages_seen}; result truncated "
                f"at {len(aggregated)} threads. Reason: cursor_missing.",
                stacklevel=2,
            )
            logger.warning(
                "op=review_threads_failed pr=%d owner=%s repo=%s "
                "page=%d aggregated=%d reason=cursor_missing",
                pull_request, owner, repo, pages_seen, len(aggregated),
            )
            break
    else:
        _warn_review_threads_capped(pull_request, len(aggregated))

    unresolved = filter_unresolved_threads(aggregated)
    logger.info(
        "op=review_threads_complete pr=%d owner=%s repo=%s "
        "pages=%d total=%d unresolved=%d duration_ms=%d",
        pull_request, owner, repo, pages_seen,
        len(aggregated), len(unresolved),
        int((time.monotonic() - op_start) * 1000),
    )
    return unresolved


# ---------------------------------------------------------------------------
# Rate limits
# ---------------------------------------------------------------------------

DEFAULT_RATE_THRESHOLDS: dict[str, int] = {
    "core": 100,
    "search": 15,
    "code_search": 5,
    "graphql": 100,
}


def check_workflow_rate_limit(
    resource_thresholds: dict[str, int] | None = None,
) -> RateLimitResult:
    """Check GitHub API rate limits before workflow execution.

    Args:
        resource_thresholds: Map of resource name to minimum remaining threshold.

    Returns:
        RateLimitResult with pass/fail per resource and markdown summary.
    """
    if resource_thresholds is None:
        resource_thresholds = dict(DEFAULT_RATE_THRESHOLDS)

    result = subprocess.run(
        ["gh", "api", "rate_limit"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to fetch rate limits: {result.stderr}")

    try:
        rate_limit = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Rate limit response was not valid JSON: {exc}") from exc

    resources: dict[str, dict] = {}
    all_passed = True
    summary_lines = [
        "### API Rate Limit Status",
        "",
        "| Resource | Remaining | Threshold | Status |",
        "|----------|-----------|-----------|--------|",
    ]

    for resource, threshold in resource_thresholds.items():
        resource_data = rate_limit.get("resources", {}).get(resource)
        if resource_data is None:
            warnings.warn(
                f"Resource '{resource}' not found in rate limit response",
                stacklevel=2,
            )
            all_passed = False
            summary_lines.append(f"| {resource} | N/A | {threshold} | X MISSING |")
            continue

        remaining = resource_data["remaining"]
        limit = resource_data["limit"]
        reset = resource_data["reset"]
        passed = remaining >= threshold

        if not passed:
            all_passed = False

        status = "OK" if passed else "TOO LOW"
        status_icon = "+" if passed else "X"

        resources[resource] = {
            "Remaining": remaining,
            "Limit": limit,
            "Reset": reset,
            "Threshold": threshold,
            "Passed": passed,
        }

        summary_lines.append(
            f"| {resource} | {remaining} | {threshold} | {status_icon} {status} |"
        )

    return RateLimitResult(
        success=all_passed,
        resources=resources,
        summary_markdown="\n".join(summary_lines),
        core_remaining=rate_limit.get("resources", {}).get("core", {}).get("remaining", 0),
    )
