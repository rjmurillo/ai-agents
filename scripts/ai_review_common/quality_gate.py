"""Quality gate: verdict parsing, label/milestone extraction, retry, workflows."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
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
# Verdict parsing
# ---------------------------------------------------------------------------

_VERDICT_PATTERN = re.compile(r"VERDICT:\s*([A-Z_]+)")

_KEYWORD_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"CRITICAL_FAIL|critical failure|severe issue", re.IGNORECASE), "CRITICAL_FAIL"),
    (re.compile(r"REJECTED|reject|must fix|blocking", re.IGNORECASE), "REJECTED"),
    (re.compile(r"PASS|approved|looks good|no issues", re.IGNORECASE), "PASS"),
    (re.compile(r"WARN|warning|caution", re.IGNORECASE), "WARN"),
]


def get_verdict(output: str) -> str:
    """Parse verdict from AI output.

    Tries explicit ``VERDICT:`` pattern first, then falls back to keyword detection.

    Common values: PASS, WARN, FAIL, REJECTED, CRITICAL_FAIL, NEEDS_REVIEW.
    """
    if not output or not output.strip():
        return "CRITICAL_FAIL"

    match = _VERDICT_PATTERN.search(output)
    if match:
        return match.group(1)

    for pattern, verdict in _KEYWORD_RULES:
        if pattern.search(output):
            return verdict

    return "CRITICAL_FAIL"


# ---------------------------------------------------------------------------
# Label / milestone parsing (LABEL: / MILESTONE: format)
# ---------------------------------------------------------------------------

_LABEL_PATTERN = re.compile(r"LABEL:\s*(\S+)")
_MILESTONE_PATTERN = re.compile(r"MILESTONE:\s*(\S+)")


def get_labels(output: str) -> list[str]:
    """Extract ``LABEL:`` entries from AI output."""
    if not output or not output.strip():
        return []
    return [m.group(1) for m in _LABEL_PATTERN.finditer(output) if m.group(1).strip()]


def get_milestone(output: str) -> str:
    """Extract ``MILESTONE:`` entry from AI output. Returns empty string if absent."""
    if not output or not output.strip():
        return ""
    match = _MILESTONE_PATTERN.search(output)
    return match.group(1) if match else ""


# ---------------------------------------------------------------------------
# Verdict aggregation
# ---------------------------------------------------------------------------

FAIL_VERDICTS = frozenset({"CRITICAL_FAIL", "REJECTED", "FAIL", "NEEDS_REVIEW"})


def merge_verdicts(verdicts: list[str]) -> str:
    """Aggregate multiple verdicts: CRITICAL_FAIL/REJECTED/FAIL/NEEDS_REVIEW > WARN > PASS."""
    if not verdicts:
        return "PASS"

    for v in verdicts:
        if v in FAIL_VERDICTS:
            return "CRITICAL_FAIL"

    if "WARN" in verdicts:
        return "WARN"

    return "PASS"


# ---------------------------------------------------------------------------
# Failure categorization
# ---------------------------------------------------------------------------

_INFRA_PATTERNS = re.compile(
    "|".join([
        r"timed?\s*out",
        r"timeout",
        r"rate\s*limit",
        r"429",
        r"network\s*error",
        r"502\s*Bad\s*Gateway",
        r"503\s*Service\s*Unavailable",
        r"connection\s*(refused|reset|timeout)",
        r"Copilot\s*CLI\s*failed.*with\s*no\s*output",
        r"missing\s*Copilot\s*access",
        r"insufficient\s*scopes",
    ]),
    re.IGNORECASE,
)


def get_failure_category(
    message: str = "",
    stderr: str = "",
    exit_code: int = 0,
    verdict: str = "",
) -> str:
    """Categorize failure as INFRASTRUCTURE or CODE_QUALITY.

    Infrastructure failures (timeouts, rate limits, network errors)
    should not block PRs, while code quality failures should.
    """
    if exit_code == 124:
        return "INFRASTRUCTURE"

    if message and message.strip() and _INFRA_PATTERNS.search(message):
        return "INFRASTRUCTURE"

    if stderr and stderr.strip() and _INFRA_PATTERNS.search(stderr):
        return "INFRASTRUCTURE"

    if (not message or not message.strip()) and (not stderr or not stderr.strip()):
        return "INFRASTRUCTURE"

    return "CODE_QUALITY"


# ---------------------------------------------------------------------------
# Spec validation
# ---------------------------------------------------------------------------

_TRACE_FAILURES = frozenset({"CRITICAL_FAIL", "FAIL", "NEEDS_REVIEW"})
_COMPLETENESS_FAILURES = frozenset({"CRITICAL_FAIL", "FAIL", "PARTIAL", "NEEDS_REVIEW"})


def spec_validation_failed(
    trace_verdict: str,
    completeness_verdict: str,
) -> bool:
    """Return True if spec validation should block merge.

    Normalizes verdicts to uppercase for case-insensitive comparison.
    """
    trace_upper = trace_verdict.upper() if trace_verdict else ""
    completeness_upper = completeness_verdict.upper() if completeness_verdict else ""
    return trace_upper in _TRACE_FAILURES or completeness_upper in _COMPLETENESS_FAILURES


# ---------------------------------------------------------------------------
# Security-hardened JSON parsing (labels / milestones)
# ---------------------------------------------------------------------------

_JSON_LABELS_PATTERN = re.compile(r'"labels"\s*:\s*\[([^\]]*)\]')
_JSON_MILESTONE_PATTERN = re.compile(r'"milestone"\s*:\s*"([^"]*)"')

# Strict validation: alphanumeric start, optional middle with safe chars,
# alphanumeric end, max 50 chars total.
SAFE_NAME_PATTERN = re.compile(
    r"^(?=.{1,50}$)[A-Za-z0-9](?:[A-Za-z0-9 _.\-]*[A-Za-z0-9])?$"
)


def get_labels_from_ai_output(output: str | None) -> list[str]:
    """Parse labels from AI JSON output with security hardening.

    Validates each label against a strict pattern that blocks
    shell metacharacters (; | ` $ etc.) and enforces length limits.
    """
    if not output or not output.strip():
        return []

    match = _JSON_LABELS_PATTERN.search(output)
    if not match:
        return []

    array_content = match.group(1)
    if not array_content or not array_content.strip():
        return []

    labels: list[str] = []
    for raw in array_content.split(","):
        label = raw.strip().strip('"').strip("'")
        if not label or not label.strip():
            continue
        if SAFE_NAME_PATTERN.match(label):
            labels.append(label)
    return labels


def get_milestone_from_ai_output(output: str | None) -> str | None:
    """Parse milestone from AI JSON output with security hardening.

    Returns None if the milestone is missing, empty, or fails validation.
    """
    if not output or not output.strip():
        return None

    match = _JSON_MILESTONE_PATTERN.search(output)
    if not match:
        return None

    milestone = match.group(1)
    if not milestone or not milestone.strip():
        return None

    if SAFE_NAME_PATTERN.match(milestone):
        return milestone
    return None


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

    try:
        all_runs: list[dict[str, Any]] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON from workflow runs for PR #{pr_number}: {exc}"
        ) from exc
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
