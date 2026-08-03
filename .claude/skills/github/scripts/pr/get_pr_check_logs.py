#!/usr/bin/env python3
"""Fetch logs from failing GitHub Actions checks on a Pull Request.

Retrieves failure logs from GitHub Actions workflow runs associated with
failing PR checks. Extracts relevant failure snippets with configurable context.

Supports standalone mode (provide --pull-request) and pipeline mode
(provide --checks-input with JSON from get_pr_checks.py).

Exit codes follow ADR-035:
    0 - Success (logs retrieved, or no failing checks)
    1 - Invalid parameters
    2 - PR not found
    3 - API error
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import re
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
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    resolve_repo_params,
)
from github_core.output import (  # noqa: E402
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

# ---------------------------------------------------------------------------
# Failure detection patterns
# ---------------------------------------------------------------------------

# Weak signals: single failure words. They also appear inside a step's own
# ``run:`` source echoed at the top of the log, so they yield false positives
# (for example ``echo "::error::..."`` or an action input ``fail-on-cache-miss``).
_WEAK_FAILURE_PATTERNS = [
    r"\berror\b",
    r"\bfail(ed|ure|ing)?\b",
    r"\btraceback\b",
    r"\bexception\b",
    r"\bpanic\b",
    r"\bfatal\b",
    r"\btimeout\b",
    r"ERROR:",
    r"\bsegmentation fault\b",
    r"\bstack trace\b",
    r"\bassertion failed\b",
]

# Authoritative signals: emitted verdicts and exit markers, not quoted source.
# GitHub Actions renders a real ``::error::`` command as ``##[error]`` in the
# downloaded log and ends a failed step with ``Process completed with exit code
# N``; the repo's review axes print a ``Verdict:`` line and an ``Exit Code:``
# line. These outrank the weak words so a tail verdict is never crowded out of
# the bounded snippet by echoed setup source (issue #3113).
_AUTHORITATIVE_PATTERNS = [
    r"##\[error\]",
    r"Process completed with exit code [1-9]",
    r"\bExit Code:\s*[1-9]",
    r"\bVerdict:\s*\w*FAIL",
]

_FAILURE_PATTERNS = _WEAK_FAILURE_PATTERNS + _AUTHORITATIVE_PATTERNS

_COMBINED_PATTERN = re.compile("|".join(_FAILURE_PATTERNS), re.IGNORECASE)
_AUTHORITATIVE_PATTERN = re.compile("|".join(_AUTHORITATIVE_PATTERNS), re.IGNORECASE)

# Fallback list used only when an input check lacks producer-computed
# "IsFailing". Keep aligned with get_pr_checks.py failing CheckRun conclusions,
# plus "ERROR" for StatusContext failures. See #2291.
_FAILING_CONCLUSIONS = (
    "FAILURE",
    "CANCELLED",
    "TIMED_OUT",
    "ACTION_REQUIRED",
    "STALE",
    "STARTUP_FAILURE",
    "ERROR",
)


def _is_failing(check: object) -> bool:
    """Return True if a normalized check object represents a failing check.

    Prefer the producer-computed ``IsFailing`` flag from get_pr_checks.py
    (authoritative for both CheckRun and StatusContext, including the ERROR
    state). Fall back to the ``Conclusion`` field only when ``IsFailing`` is
    absent, so callers that pipe minimal check data still work.
    """
    if not isinstance(check, dict):
        raise TypeError("check must be a dict")
    flag = check.get("IsFailing")
    if flag is not None:
        return bool(flag)
    return check.get("Conclusion") in _FAILING_CONCLUSIONS


# ---------------------------------------------------------------------------
# URL parsing helpers
# ---------------------------------------------------------------------------


def get_run_id_from_url(url: str) -> str | None:
    """Extract workflow run ID from a GitHub Actions URL."""
    match = re.search(r"/actions/runs/(\d+)", url)
    return match.group(1) if match else None


def get_job_id_from_url(url: str) -> str | None:
    """Extract job ID from a GitHub Actions URL."""
    match = re.search(r"/job/(\d+)", url)
    return match.group(1) if match else None


def is_github_actions_url(url: str) -> bool:
    """Check if URL points to GitHub Actions."""
    return bool(re.search(r"github\.com/.+/actions/runs/", url or ""))


# ---------------------------------------------------------------------------
# Log fetching and parsing
# ---------------------------------------------------------------------------


def _unwrap_checks_payload(checks_data: dict[str, object]) -> dict[str, object] | None:
    """Return the checks payload, or None when the envelope is malformed."""
    if "Data" not in checks_data:
        return checks_data
    payload = checks_data["Data"]
    return payload if isinstance(payload, dict) else None


def _coerce_checks_list(payload: dict[str, object]) -> list[dict[str, Any]] | None:
    """Return a checked list of check objects, or None when malformed."""
    checks_value = payload.get("Checks")
    if checks_value is None:
        return []
    if not isinstance(checks_value, list):
        return None
    if not all(isinstance(check, dict) for check in checks_value):
        return None
    return checks_value


def _merge_ref_unusable(payload: dict[str, object]) -> bool:
    """Return True when get_pr_checks reports an unusable merge ref."""
    return payload.get("MergeRefUsable") is False


def _write_merge_ref_warning(payload: dict[str, object], fmt: str) -> None:
    """Emit a non-fatal warning when the merge ref is unusable.

    Unlike the original hard-exit version, this prints a human-readable
    warning and returns so the caller can still fetch logs for any checks
    that have a known DetailsUrl (issue #3911).
    """
    warning = payload.get("MergeStateWarning")
    message = (
        warning
        if isinstance(warning, str) and warning
        else "PR merge ref cannot be built; check logs are incomplete"
    )
    print(f"[WARNING] {message}", file=sys.stderr)


def _write_merge_ref_error(payload: dict[str, object], fmt: str) -> None:
    warning = payload.get("MergeStateWarning")
    message = (
        warning
        if isinstance(warning, str) and warning
        else "PR merge ref cannot be built; check logs are incomplete"
    )
    write_skill_error(
        message,
        1,
        error_type="VerificationFailed",
        output_format=fmt,
        script_name="get_pr_check_logs.py",
    )


def _rank_matches(log_lines: list[str]) -> list[int]:
    """Return failure-matching line indices, most authoritative first.

    Authoritative markers rank before weak word matches; within a tier the
    later line wins, so a tail verdict beats echoed setup source (#3113).
    """
    matches = [i for i, line in enumerate(log_lines) if _COMBINED_PATTERN.search(line)]
    return sorted(
        matches,
        key=lambda i: (0 if _AUTHORITATIVE_PATTERN.search(log_lines[i]) else 1, -i),
    )


def _claim_lines(
    ranked: list[int],
    line_count: int,
    context_lines: int,
    max_lines: int,
) -> set[int]:
    """Claim context windows around ranked matches until the budget fills."""
    claimed: set[int] = set()
    for i in ranked:
        if len(claimed) >= max_lines:
            break
        if i in claimed:
            continue
        start = max(0, i - context_lines)
        end = min(line_count - 1, i + context_lines)
        fresh = [n for n in range(start, end + 1) if n not in claimed]
        remaining = max_lines - len(claimed)
        claimed.update(fresh[:remaining])
    return claimed


def _group_runs(sorted_lines: list[int]) -> list[tuple[int, int]]:
    """Collapse a sorted line-index list into contiguous (start, end) runs."""
    runs: list[tuple[int, int]] = []
    start = prev = sorted_lines[0]
    for n in sorted_lines[1:]:
        if n == prev + 1:
            prev = n
            continue
        runs.append((start, prev))
        start = prev = n
    runs.append((start, prev))
    return runs


def _run_has_authoritative(run: tuple[int, int], log_lines: list[str]) -> bool:
    start, end = run
    return any(_AUTHORITATIVE_PATTERN.search(log_lines[n]) for n in range(start, end + 1))


def _run_to_snippet(start: int, end: int, log_lines: list[str]) -> dict[str, object]:
    """Build a snippet dict for a claimed run, keyed on its best match line."""
    matches = [n for n in range(start, end + 1) if _COMBINED_PATTERN.search(log_lines[n])]
    authoritative = [n for n in matches if _AUTHORITATIVE_PATTERN.search(log_lines[n])]
    rep = authoritative[0] if authoritative else (matches[0] if matches else start)
    return {
        "LineNumber": rep + 1,
        "MatchedLine": log_lines[rep].strip(),
        "Context": "\n".join(log_lines[start : end + 1]),
        "StartLine": start + 1,
        "EndLine": end + 1,
    }


def get_failure_snippets(
    log_lines: list[str],
    context_lines: int,
    max_lines: int,
) -> list[dict[str, object]]:
    """Extract failure snippets, prioritizing authoritative verdicts.

    GitHub Actions echoes a step's own ``run:`` source at the top of the log.
    Weak word matches inside that echoed source used to consume the whole
    ``max_lines`` budget before the scan reached the real verdict near the tail
    (issue #3113). Matches are now ranked (authoritative markers first, then
    later-in-log before earlier), claimed within budget, and overlapping
    windows merged, so the authoritative failure always lands in the snippet.
    Authoritative snippets are returned before weak ones.
    """
    ranked = _rank_matches(log_lines)
    claimed = _claim_lines(ranked, len(log_lines), context_lines, max_lines)
    if not claimed:
        return []
    runs = _group_runs(sorted(claimed))
    runs.sort(key=lambda r: (0 if _run_has_authoritative(r, log_lines) else 1, r[0]))
    return [_run_to_snippet(start, end, log_lines) for start, end in runs]


def fetch_workflow_run_logs(
    owner: str,
    repo: str,
    run_id: str,
    job_id: str | None,
) -> dict[str, object]:
    """Fetch logs for a GitHub Actions workflow run."""
    # Try job-specific logs first
    if job_id:
        result = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/actions/jobs/{job_id}/logs"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout:
            return {"Success": True, "Content": result.stdout, "Source": "job"}

    # Fall back to run view --log-failed
    result = subprocess.run(
        ["gh", "run", "view", run_id, "--repo", f"{owner}/{repo}", "--log-failed"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode == 0 and result.stdout:
        return {"Success": True, "Content": result.stdout, "Source": "run-failed"}

    # Try full log
    result = subprocess.run(
        ["gh", "run", "view", run_id, "--repo", f"{owner}/{repo}", "--log"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode == 0 and result.stdout:
        return {"Success": True, "Content": result.stdout, "Source": "run-full"}

    return {
        "Success": False,
        "Error": f"Failed to fetch logs: {result.stderr}",
        "Source": "none",
    }


def get_check_logs(
    owner: str,
    repo: str,
    failing_checks: list[dict[str, Any]],
    max_lines: int,
    context_lines: int,
) -> list[dict[str, object]]:
    """Fetch logs for all failing checks."""
    results: list[dict[str, object]] = []

    for check in failing_checks:
        check_result: dict[str, object] = {
            "Name": check.get("Name", ""),
            "DetailsUrl": check.get("DetailsUrl", ""),
            "State": check.get("State", ""),
            "Conclusion": check.get("Conclusion", ""),
        }

        details_url = check.get("DetailsUrl", "")

        if not is_github_actions_url(details_url):
            check_result["LogSource"] = "external"
            check_result["Note"] = "External CI system, logs not accessible via GitHub API"
            check_result["Snippets"] = []
            results.append(check_result)
            continue

        run_id = get_run_id_from_url(details_url)
        job_id = get_job_id_from_url(details_url)

        if not run_id:
            check_result["LogSource"] = "error"
            check_result["Error"] = "Could not extract run ID from URL"
            check_result["Snippets"] = []
            results.append(check_result)
            continue

        check_result["RunId"] = run_id
        if job_id:
            check_result["JobId"] = job_id

        log_result = fetch_workflow_run_logs(owner, repo, run_id, job_id)

        if not log_result["Success"]:
            check_result["LogSource"] = "error"
            check_result["Error"] = log_result.get("Error", "Unknown error")
            check_result["Snippets"] = []
            results.append(check_result)
            continue

        check_result["LogSource"] = log_result["Source"]

        content = log_result["Content"]
        log_lines = content.splitlines() if isinstance(content, str) else []

        snippets = get_failure_snippets(log_lines, context_lines, max_lines)
        check_result["Snippets"] = snippets
        check_result["TotalLogLines"] = len(log_lines)

        results.append(check_result)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch logs from failing GitHub Actions checks on a PR.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request",
        type=int,
        default=0,
        help="PR number (standalone mode)",
    )
    parser.add_argument(
        "--checks-input",
        default="",
        help="JSON string from get_pr_checks.py output (pipeline mode). Use '-' for stdin.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=160,
        help="Maximum lines to extract per failure snippet (default: 160)",
    )
    parser.add_argument(
        "--context-lines",
        type=int,
        default=30,
        help="Lines of context before/after failure markers (default: 30)",
    )
    add_output_format_arg(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved.owner
    repo = resolved.repo

    fmt = get_output_format(args.output_format)
    pr_number = args.pull_request
    failing_checks: list[dict[str, Any]] = []
    merge_ref_unusable = False
    merge_ref_payload: dict[str, object] = {}
    merge_ref_warning: str | None = None

    checks_input = args.checks_input
    if checks_input == "-":
        checks_input = sys.stdin.read()

    if checks_input:
        # Pipeline mode
        try:
            checks_data = json.loads(checks_input)
        except json.JSONDecodeError as exc:
            write_skill_error(
                f"Failed to parse checks input: {exc}",
                1,
                error_type="InvalidParams",
                output_format=fmt,
                script_name="get_pr_check_logs.py",
            )
            return 1

        if not checks_data.get("Success"):
            write_skill_error(
                f"Input checks data indicates failure: {checks_data.get('Error', '')}",
                1,
                error_type="InvalidParams",
                output_format=fmt,
                script_name="get_pr_check_logs.py",
            )
            return 1

        # get_pr_checks.py wraps its payload in a standard skill envelope:
        # {"Success": true, "Data": {"Number": ..., "Checks": [...]}, ...}
        # Tolerate both the enveloped form (new) and bare form (legacy / tests)
        # by falling back to the top-level object when "Data" is absent.
        payload = _unwrap_checks_payload(checks_data)
        if payload is None:
            write_skill_error(
                "Checks response contains malformed Data payload",
                1,
                error_type="InvalidParams",
                output_format=fmt,
                script_name="get_pr_check_logs.py",
            )
            return 1

        if payload.get("Number") and pr_number == 0:
            pr_number = payload["Number"]

        merge_ref_unusable = _merge_ref_unusable(payload)
        if merge_ref_unusable:
            _write_merge_ref_warning(payload, fmt)
            merge_ref_payload = payload

        checks_list = _coerce_checks_list(payload)
        if checks_list is None:
            if merge_ref_unusable:
                _write_merge_ref_error(payload, fmt)
                return 1
            write_skill_error(
                "Checks response contains malformed Checks payload",
                1,
                error_type="InvalidParams",
                output_format=fmt,
                script_name="get_pr_check_logs.py",
            )
            return 1

        failing_checks = [c for c in checks_list if _is_failing(c)]
        if merge_ref_unusable:
            if not any(c.get("DetailsUrl") for c in failing_checks):
                _write_merge_ref_error(payload, fmt)
                return 1
            merge_ref_warning = (
                str(payload.get("MergeStateWarning") or "")
                or "PR merge ref unusable; logs may be incomplete"
            )

    elif pr_number > 0:
        # Standalone mode - fetch checks first
        checks_script = os.path.join(os.path.dirname(__file__), "get_pr_checks.py")
        result = subprocess.run(
            [
                sys.executable,
                checks_script,
                "--owner",
                owner,
                "--repo",
                repo,
                "--pull-request",
                str(pr_number),
                "--output-format",
                "json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

        # Exit codes 2, 3, 7 are actual errors
        if result.returncode in (2, 3, 7):
            print(result.stdout)
            return result.returncode

        try:
            checks_data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            write_skill_error(
                f"Failed to parse checks response: {exc}",
                3,
                error_type="ApiError",
                output_format=fmt,
                script_name="get_pr_check_logs.py",
            )
            return 3

        if not checks_data.get("Success"):
            print(result.stdout)
            return 2

        # Same envelope-tolerant unwrap as pipeline mode above
        payload = _unwrap_checks_payload(checks_data)
        if payload is None:
            write_skill_error(
                "Checks response contains malformed Data payload",
                3,
                error_type="ApiError",
                output_format=fmt,
                script_name="get_pr_check_logs.py",
            )
            return 3
        merge_ref_unusable = _merge_ref_unusable(payload)
        if merge_ref_unusable:
            _write_merge_ref_warning(payload, fmt)
            merge_ref_payload = payload
        checks_list = _coerce_checks_list(payload)
        if checks_list is None:
            if merge_ref_unusable:
                _write_merge_ref_error(payload, fmt)
                return 1
            write_skill_error(
                "Checks response contains malformed Checks payload",
                1,
                error_type="InvalidParams",
                output_format=fmt,
                script_name="get_pr_check_logs.py",
            )
            return 1

        failing_checks = [c for c in checks_list if _is_failing(c)]
        if merge_ref_unusable:
            if not any(c.get("DetailsUrl") for c in failing_checks):
                _write_merge_ref_error(payload, fmt)
                return 1
            merge_ref_warning = (
                str(payload.get("MergeStateWarning") or "")
                or "PR merge ref unusable; logs may be incomplete"
            )
    else:
        write_skill_error(
            "Either --pull-request or --checks-input is required",
            1,
            error_type="InvalidParams",
            output_format=fmt,
            script_name="get_pr_check_logs.py",
        )
        return 1

    # No failing checks
    if not failing_checks:
        if merge_ref_unusable:
            # Merge ref is unusable AND no failing checks visible: the check set
            # is incomplete. Return non-zero so callers know logs are unavailable.
            _write_merge_ref_error(merge_ref_payload, fmt)
            return 1
        output = {
            "Owner": owner,
            "Repo": repo,
            "PullRequest": pr_number,
            "FailingChecks": 0,
            "Message": "No failing checks found",
            "CheckLogs": [],
        }
        write_skill_output(
            output,
            output_format=fmt,
            human_summary="No failing checks to analyze",
            status="PASS",
            script_name="get_pr_check_logs.py",
        )
        return 0

    # Fetch logs
    check_logs = get_check_logs(
        owner,
        repo,
        failing_checks,
        args.max_lines,
        args.context_lines,
    )

    output = {
        "Owner": owner,
        "Repo": repo,
        "PullRequest": pr_number,
        "FailingChecks": len(failing_checks),
        "CheckLogs": check_logs,
    }
    if merge_ref_warning:
        output["MergeRefWarning"] = merge_ref_warning

    logs_found = sum(1 for cl in check_logs if cl.get("Snippets"))
    external = sum(1 for cl in check_logs if cl.get("LogSource") == "external")

    if external > 0:
        summary = (
            f"Analyzed {len(failing_checks)} failing check(s): "
            f"{logs_found} with logs, {external} external (logs not accessible)"
        )
    else:
        summary = (
            f"Analyzed {len(failing_checks)} failing check(s) "
            f"with {logs_found} containing failure snippets"
        )

    write_skill_output(
        output,
        output_format=fmt,
        human_summary=summary,
        status="FAIL" if failing_checks else "PASS",
        script_name="get_pr_check_logs.py",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
