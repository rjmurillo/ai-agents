"""GitHub API helpers for skill scripts.

Wraps gh CLI for authentication, repository inference, GraphQL queries,
and paginated REST API calls. All functions use subprocess to call gh CLI.
"""

import json
import re
import subprocess
import sys

from github_core.validation import test_github_name_valid


def _run_gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a gh CLI command and return the result.

    Args:
        *args: Arguments to pass to gh.
        check: If False, don't raise on non-zero exit.

    Returns:
        CompletedProcess with stdout/stderr.
    """
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, ["gh", *args], result.stdout, result.stderr
        )
    return result


def write_error_and_exit(message: str, exit_code: int) -> None:
    """Write error to stderr and exit with the specified code.

    Args:
        message: Error message.
        exit_code: ADR-035 exit code.
    """
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(exit_code)


def test_gh_authenticated() -> bool:
    """Check if GitHub CLI is installed and authenticated."""
    result = _run_gh("auth", "status", check=False)
    return result.returncode == 0


def assert_gh_authenticated() -> None:
    """Ensure GitHub CLI is authenticated. Exit 4 if not."""
    if not test_gh_authenticated():
        write_error_and_exit(
            "GitHub CLI (gh) is not installed or not authenticated. Run 'gh auth login' first.",
            4,
        )


def get_repo_info() -> dict | None:
    """Infer repository owner and name from git remote.

    Returns:
        Dict with 'owner' and 'repo' keys, or None if not in a git repo.
    """
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None

    match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", result.stdout.strip())
    if match:
        return {
            "owner": match.group(1),
            "repo": match.group(2).removesuffix(".git"),
        }
    return None


def resolve_repo_params(owner: str | None = None, repo: str | None = None) -> dict:
    """Resolve owner and repo, inferring from git remote if needed.

    Args:
        owner: Repository owner (optional).
        repo: Repository name (optional).

    Returns:
        Dict with 'owner' and 'repo' keys.

    Exits with code 1 if cannot be determined or names are invalid.
    """
    if not owner or not repo:
        info = get_repo_info()
        if info:
            owner = owner or info["owner"]
            repo = repo or info["repo"]
        else:
            write_error_and_exit(
                "Could not infer repository info. Provide --owner and --repo.",
                1,
            )

    # After fallback resolution, owner and repo are guaranteed non-None.
    # write_error_and_exit calls sys.exit, so control only reaches here
    # when both values are set.
    assert owner is not None
    assert repo is not None

    if not test_github_name_valid(owner, "owner"):
        write_error_and_exit(f"Invalid GitHub owner name: {owner}", 1)
    if not test_github_name_valid(repo, "repo"):
        write_error_and_exit(f"Invalid GitHub repository name: {repo}", 1)

    return {"owner": owner, "repo": repo}


def gh_graphql(query: str, variables: dict | None = None) -> dict:
    """Execute a GitHub GraphQL query or mutation.

    Passes the full request body as JSON via stdin to prevent LFI attacks.
    The gh CLI -f flag treats values starting with @ as file paths, so
    we avoid -f for user-controlled values entirely.

    Args:
        query: GraphQL query/mutation string.
        variables: Dict of variables to pass.

    Returns:
        Parsed JSON response data.

    Raises:
        subprocess.CalledProcessError on API failure.
    """
    body = {"query": query}
    if variables:
        body["variables"] = variables

    result = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        input=json.dumps(body),
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)

    if "errors" in data:
        error_msg = "; ".join(e.get("message", str(e)) for e in data["errors"])
        raise RuntimeError(f"GraphQL error: {error_msg}")

    response: dict = data.get("data", data)
    return response


def gh_api_paginated(endpoint: str, page_size: int = 100) -> list:
    """Fetch all pages from a GitHub REST API endpoint.

    Args:
        endpoint: API endpoint path (e.g., "repos/owner/repo/pulls/1/comments").
        page_size: Items per page (max 100).

    Returns:
        List of all items across all pages.
    """
    all_items = []
    page = 1
    separator = "&" if "?" in endpoint else "?"

    while True:
        url = f"{endpoint}{separator}per_page={page_size}&page={page}"
        result = _run_gh("api", url, check=False)

        if result.returncode != 0:
            if page == 1:
                write_error_and_exit(
                    f"GitHub API request failed for '{endpoint}': {result.stderr}",
                    3,
                )
            break

        items = json.loads(result.stdout)
        if not items:
            break

        all_items.extend(items)

        if len(items) < page_size:
            break

        page += 1

    return all_items
