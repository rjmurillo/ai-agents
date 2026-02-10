"""Runtime, logging, environment validation, and workflow analysis."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (mirrors PowerShell $script: variables)
# ---------------------------------------------------------------------------

_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY = 30


def _get_config_int(env_var: str, default: int) -> int:
    raw = os.environ.get(env_var, "")
    if raw.strip().isdigit():
        return int(raw)
    return default


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


def initialize_ai_review(review_dir: str | None = None) -> str:
    """Create the AI review working directory if it does not exist.

    Returns the path to the directory.
    """
    if review_dir is None:
        review_dir = os.environ.get("AI_REVIEW_DIR", "")
        if not review_dir:
            temp = os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"
            review_dir = os.path.join(temp, "ai-review")

    Path(review_dir).mkdir(parents=True, exist_ok=True)
    return review_dir


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


def invoke_with_retry[T](
    func: Callable[[], T],
    max_retries: int | None = None,
    initial_delay: int | None = None,
) -> T:
    """Execute *func* with exponential backoff on failure.

    Raises the last exception after all retries are exhausted.
    """
    if max_retries is None:
        max_retries = _get_config_int("MAX_RETRIES", _DEFAULT_MAX_RETRIES)
    if initial_delay is None:
        initial_delay = _get_config_int("RETRY_DELAY", _DEFAULT_RETRY_DELAY)

    delay = initial_delay
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            if attempt == max_retries:
                raise RuntimeError(
                    f"All {max_retries} attempts failed. Last error: {exc}"
                ) from exc
            logger.warning(
                "Attempt %d/%d failed, retrying in %ds...",
                attempt,
                max_retries,
                delay,
            )
            time.sleep(delay)
            delay *= 2

    # Unreachable, but satisfies type checker
    raise RuntimeError(f"All {max_retries} attempts failed. Last error: {last_error}")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def write_log(message: str) -> None:
    """Log a timestamped informational message."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    logger.info("[%s] %s", timestamp, message)


def write_log_error(message: str) -> None:
    """Log a timestamped error message."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    logger.error("[%s] ERROR: %s", timestamp, message)


# ---------------------------------------------------------------------------
# Environment validation
# ---------------------------------------------------------------------------


def assert_environment_variables(names: list[str]) -> None:
    """Validate that all specified environment variables are set and non-empty.

    Raises RuntimeError listing all missing variables.
    """
    missing = [n for n in names if not os.environ.get(n, "").strip()]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# PR changed files
# ---------------------------------------------------------------------------


def get_pr_changed_files(pr_number: int, pattern: str = ".*") -> list[str]:
    """Get changed files in a PR, optionally filtered by regex *pattern*.

    Uses the GitHub files API (avoids HTTP 406 on large diffs).
    """
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        try:
            result = subprocess.run(
                ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            repo = result.stdout.strip() if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    if not repo:
        return []

    try:
        result = subprocess.run(
            [
                "gh", "api",
                f"repos/{repo}/pulls/{pr_number}/files",
                "--paginate",
                "--jq", ".[].filename",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        compiled = re.compile(pattern)
        return [f for f in result.stdout.strip().split("\n") if compiled.search(f)]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


# ---------------------------------------------------------------------------
# Workflow run analysis
# ---------------------------------------------------------------------------


def get_workflow_runs_by_pr(
    pr_number: int,
    workflow_name: str | None = None,
    repository: str | None = None,
) -> list[dict[str, Any]]:
    """Get all workflow runs for a specific PR.

    Queries GitHub Actions API and filters to runs associated with *pr_number*.
    """
    if not repository:
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", result.stdout)
            if match:
                repository = f"{match.group(1)}/{match.group(2)}"
            else:
                raise RuntimeError("Could not determine repository from git remote")
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            raise RuntimeError("Could not determine repository from git remote") from exc

    result = subprocess.run(
        [
            "gh", "api",
            f"/repos/{repository}/actions/runs?event=pull_request&per_page=100",
            "--jq", ".workflow_runs",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to get workflow runs for PR #{pr_number}: {result.stderr.strip()}"
        )

    all_runs: list[dict[str, Any]] = json.loads(result.stdout)
    pr_runs = [
        run
        for run in all_runs
        if run.get("pull_requests")
        and any(pr.get("number") == pr_number for pr in run["pull_requests"])
    ]

    if workflow_name:
        pr_runs = [r for r in pr_runs if workflow_name in r.get("name", "")]

    return pr_runs


def runs_overlap(run1: dict[str, Any], run2: dict[str, Any]) -> bool:
    """Check if two workflow runs overlap in time."""
    run1_start = datetime.fromisoformat(run1["created_at"].replace("Z", "+00:00"))
    run1_end = datetime.fromisoformat(run1["updated_at"].replace("Z", "+00:00"))
    run2_start = datetime.fromisoformat(run2["created_at"].replace("Z", "+00:00"))
    return run1_start < run2_start < run1_end


def get_concurrency_group_from_run(run: dict[str, Any]) -> str:
    """Extract concurrency group identifier from a workflow run."""
    pr_number = None
    if run.get("event") == "pull_request" and run.get("pull_requests"):
        pr_number = run["pull_requests"][0].get("number")

    if pr_number is not None:
        name = run.get("name", "")
        name_lower = name.lower()
        if "quality" in name_lower:
            prefix = "ai-quality"
        elif "spec" in name_lower:
            prefix = "spec-validation"
        elif "session" in name_lower:
            prefix = "session-protocol"
        elif "label" in name_lower:
            prefix = "label-pr"
        elif "memory" in name_lower:
            prefix = "memory-validation"
        elif "assign" in name_lower:
            prefix = "auto-assign"
        else:
            prefix = "pr-validation"
        return f"{prefix}-{pr_number}"

    return f"{run.get('name', 'unknown')}-{run.get('head_branch', 'unknown')}"
