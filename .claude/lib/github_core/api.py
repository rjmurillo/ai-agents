"""GitHub API helpers: auth, pagination, GraphQL, issue comments, rate limits.

Canonical copy lives at scripts/github_core/api.py; keep in sync.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:
    from .protocol import GitHubClient

from .validation import is_github_name_valid

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


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


def get_repo_info() -> dict[str, str] | None:
    """Infer repository owner and name from git remote origin URL.

    Returns:
        Dict with 'Owner' and 'Repo' keys, or None if not in a git repo.
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
            return {
                "Owner": match.group(1),
                "Repo": re.sub(r"\.git$", "", match.group(2)),
            }
    except subprocess.TimeoutExpired:
        logger.debug("git remote get-url origin timed out")
    except FileNotFoundError:
        logger.debug("git executable not found on PATH")
    return None


def resolve_repo_params(owner: str = "", repo: str = "") -> dict[str, str]:
    """Resolve Owner and Repo, inferring from git remote if not provided.

    Raises SystemExit if parameters cannot be determined or are invalid.

    Returns:
        Dict with 'Owner' and 'Repo' keys.
    """
    if not owner or not repo:
        repo_info = get_repo_info()
        if repo_info:
            owner = owner or repo_info["Owner"]
            repo = repo or repo_info["Repo"]
        else:
            error_and_exit(
                "Could not infer repository info. Please provide -Owner and -Repo parameters.",
                1,
            )

    if not is_github_name_valid(owner, "Owner"):
        error_and_exit(f"Invalid GitHub owner name: {owner}", 1)
    if not is_github_name_valid(repo, "Repo"):
        error_and_exit(f"Invalid GitHub repository name: {repo}", 1)

    return {"Owner": owner, "Repo": repo}


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


def get_unresolved_review_threads(
    owner: str,
    repo: str,
    pull_request: int,
) -> list[dict]:
    """Retrieve unresolved review threads on a pull request.

    Returns an empty list on API failure (never None).

    Args:
        owner: Repository owner.
        repo: Repository name.
        pull_request: PR number.

    Returns:
        List of thread dicts where isResolved is False.
    """
    query = """\
query($owner: String!, $name: String!, $prNumber: Int!) {
    repository(owner: $owner, name: $name) {
        pullRequest(number: $prNumber) {
            reviewThreads(first: 100) {
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

    try:
        data = gh_graphql(
            query,
            {"owner": owner, "name": repo, "prNumber": pull_request},
        )
    except RuntimeError as exc:
        warnings.warn(
            f"Failed to query review threads for PR #{pull_request}: {exc}",
            stacklevel=2,
        )
        return []

    threads = (
        data.get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes", [])
    )

    if not threads:
        return []

    return [t for t in threads if not t.get("isResolved", True)]


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
