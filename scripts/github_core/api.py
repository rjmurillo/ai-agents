"""GitHub API helpers: auth, pagination, GraphQL, issue comments, rate limits.

Cohesive sub-concerns live in sibling modules and are re-exported here so the
public import surface ``from scripts.github_core.api import ...`` stays stable
(Issue #1910):

- ``log_safety``: ``safe_log_str`` (CWE-117 log-forging defense).
- ``review_threads``: review-thread shape, predicates, paginated fetch,
  ``FetchStatus``, ``get_unresolved_review_threads``.
- ``rate_limit``: ``RateLimitResult``, ``DEFAULT_RATE_THRESHOLDS``,
  ``check_workflow_rate_limit``.
"""

from __future__ import annotations

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

from scripts.github_core.log_safety import safe_log_str
from scripts.github_core.rate_limit import (  # noqa: F401
    DEFAULT_RATE_THRESHOLDS,
    RateLimitResult,
    check_workflow_rate_limit,
)
from scripts.github_core.review_threads import (  # noqa: F401
    _REVIEW_THREADS_MAX_PAGES,
    _REVIEW_THREADS_QUERY,
    FetchStatus,
    _fetch_review_threads_page,
    _log_review_threads_page,
    _warn_review_threads_capped,
    count_unresolved_threads,
    filter_unresolved_threads,
    get_unresolved_review_threads,
    transform_review_thread,
)
from scripts.github_core.validation import is_github_name_valid

logger = logging.getLogger(__name__)


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


# Bounded retry policy for transient GraphQL transport failures (issue #2631).
# release-it.md: integration points are suspect; retry only transient (5xx/429)
# failures, bounded, with exponential backoff. Permanent errors fail fast.
_GRAPHQL_MAX_ATTEMPTS = 3
_GRAPHQL_BACKOFF_BASE_SECONDS = 2.0
_TRANSIENT_HTTP_PATTERN = re.compile(r"\(?\bHTTP\s+(429|500|502|503|504)\b")


def _is_transient_graphql_error(error_msg: str) -> bool:
    """Return True when the gh error text indicates a retryable upstream status.

    Transient = HTTP 429 (rate limit) or 5xx (500/502/503/504). These are
    upstream timeouts/overloads that a bounded retry can recover. Client errors
    (4xx other than 429) and GraphQL-level errors are permanent and not retried.
    """
    return _TRANSIENT_HTTP_PATTERN.search(error_msg) is not None


_RETRY_AFTER_PATTERN = re.compile(r"\bRetry-After:\s*(\d+)", re.IGNORECASE)


def _retry_after_delay(error_text: str, backoff: float) -> float:
    """Return Retry-After delay if present in error text, else backoff.

    GitHub may include ``Retry-After: <seconds>`` in gh error text for HTTP 429
    responses. Honouring it avoids hammering the rate limit instead of using
    the caller-supplied exponential backoff.
    """
    match = _RETRY_AFTER_PATTERN.search(error_text)
    if match:
        return float(match.group(1))
    return backoff


def _build_gh_graphql_args(query: str, variables: dict) -> list[str]:
    """Assemble the ``gh api graphql`` argv with typed variable flags."""
    gh_args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if isinstance(value, (int, bool)):
            gh_args.extend(["-F", f"{key}={value}"])
        else:
            gh_args.extend(["-f", f"{key}={value}"])
    return gh_args


def _extract_graphql_error(result: subprocess.CompletedProcess[str]) -> str:
    """Pull a human-readable error message out of a failed gh invocation."""
    error_msg = result.stderr.strip() or result.stdout.strip()
    msg_match = re.search(r'"message"\s*:\s*"([^"]+)"', error_msg)
    if msg_match:
        return str(msg_match.group(1))
    return error_msg


def _parse_graphql_response(stdout: str) -> dict:
    """Parse a successful gh stdout into the GraphQL ``data`` payload.

    Raises RuntimeError on unparseable output or GraphQL-level errors; both are
    permanent (not retried by the caller).
    """
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse GraphQL response: {stdout}") from exc

    if parsed.get("errors"):
        messages = [e.get("message", str(e)) for e in parsed["errors"]]
        raise RuntimeError(f"GraphQL errors: {'; '.join(messages)}")

    data: dict = parsed.get("data", {})
    return data


def gh_graphql(query: str, variables: dict | None = None) -> dict:
    """Execute a GitHub GraphQL query or mutation with bounded retry.

    Uses GraphQL variables for safe parameterization (ADR-015 compliant).
    Transient upstream failures (HTTP 429/5xx) are retried with exponential
    backoff up to ``_GRAPHQL_MAX_ATTEMPTS`` (issue #2631, release-it.md). A
    persistent transient failure, or any permanent error, still raises.

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

    gh_args = _build_gh_graphql_args(query, variables)

    for attempt in range(1, _GRAPHQL_MAX_ATTEMPTS + 1):
        result = subprocess.run(
            gh_args,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

        if result.returncode == 0:
            return _parse_graphql_response(result.stdout)

        # Check transient status against raw output BEFORE extraction (issue #2631).
        # _extract_graphql_error may strip HTTP status from messages like
        # '{"message": "..."} (HTTP 504)', so transient detection must use raw text.
        raw_error = result.stderr.strip() or result.stdout.strip()
        error_msg = _extract_graphql_error(result)
        is_last = attempt == _GRAPHQL_MAX_ATTEMPTS
        if not is_last and _is_transient_graphql_error(raw_error):
            backoff = _GRAPHQL_BACKOFF_BASE_SECONDS ** (attempt - 1)
            delay = _retry_after_delay(raw_error, backoff)
            logger.warning(
                "Transient GraphQL failure (attempt %d/%d), retrying in %.1fs: %s",
                attempt,
                _GRAPHQL_MAX_ATTEMPTS,
                delay,
                safe_log_str(error_msg),
            )
            time.sleep(delay)
            continue
        raise RuntimeError(f"GraphQL request failed: {error_msg}")

    # Unreachable: the loop either returns, retries, or raises on every path.
    raise RuntimeError("GraphQL request failed: retries exhausted")


_ALL_PRS_QUERY = """\
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


def _extract_pull_requests_page(data: dict, owner: str, repo: str) -> dict:
    """Pull the ``pullRequests`` connection out of a GraphQL response.

    Raises RuntimeError when the repository or its pullRequests field is null,
    so the caller does not have to repeat the two None checks.
    """
    repo_data = data.get("repository")
    if repo_data is None:
        raise RuntimeError(f"Repository {owner}/{repo} not found or not accessible")
    pr_data: dict | None = repo_data.get("pullRequests")
    if pr_data is None:
        raise RuntimeError(f"Could not retrieve pull requests for {owner}/{repo}")
    return pr_data


def _collect_prs_with_comments(
    nodes: list[dict],
    since: datetime,
) -> tuple[list[dict], bool]:
    """Filter one page of PR nodes to those with comments in the time range.

    Returns ``(matched, reached_since_boundary)``. ``reached_since_boundary``
    is True once a PR older than *since* is seen; since PRs are ordered by
    updatedAt DESC, that signals the caller to stop paginating.
    """
    matched: list[dict] = []
    for pr in nodes:
        updated_at = datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))
        if updated_at < since:
            return matched, True

        threads = (pr.get("reviewThreads") or {}).get("nodes") or []
        has_comments = any(
            len((t.get("comments") or {}).get("nodes") or []) > 0 for t in threads
        )
        if has_comments:
            matched.append(pr)
    return matched, False


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
    all_prs: list[dict] = []
    cursor: str | None = None
    has_next_page = True
    page_count = 0

    while has_next_page and page_count < max_pages:
        page_count += 1

        variables: dict = {"owner": owner, "repo": repo}
        if cursor:
            variables["cursor"] = cursor

        data = gh_graphql(_ALL_PRS_QUERY, variables)
        pr_data = _extract_pull_requests_page(data, owner, repo)

        matched, reached_boundary = _collect_prs_with_comments(pr_data["nodes"], since)
        all_prs.extend(matched)

        if reached_boundary:
            has_next_page = False
        else:
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
