#!/usr/bin/env python3
"""Per-PR round/time circuit breaker for pr-autofix's T3/T4 thread loop (issue #5056).

pr-autofix's thread-lifecycle loop (Phase 2, T3/T4 of the pr-autofix skill in
this install) had no machine-enforced cap on how many fix/review rounds it
runs against one PR. The lease and live-state gate protect against racing or
acting on a stale PR; neither bounds how long the loop keeps acting on a PR
that is still live and actionable. Evidence from this project's history:
PR #1887 ran 46h wall clock, 69 commits, and 11+ bot review rounds; PRs #1965
and #1979 ran 18 rounds each. Prose caps have been written down and ignored
repeatedly, which is why this one is a gate rather than a sentence.
This script follows `check_pr_live_state.py`'s shape (issue #2455): a
machine-checked JSON envelope pr-autofix branches on, not another sentence
in a SKILL.md.

Storage decision: the retired autofix lease (ADR-076) solved "small per-PR
state that survives a session restart" with a hidden-marker PR comment. This
script reuses that shape. A squash-merge, rebase, or force-push destroys the
commit history a counter would replay, while a comment lives on the issue
timeline. It needs only the GitHub API, like `check_pr_live_state.py`, and a
fourth ad-hoc storage scheme repeats the failure `.claude/rules/push-lock.md`
documents for lock files.

Unlike the lease, this marker carries no security weight: a forged or
duplicated marker at worst causes a premature ESCALATE (fail-safe), never a
bypassed cap (fail-open, the failure this script prevents). So it skips the
lease's verified-comment-author bookkeeping and trusts the latest marker
carrying this script's own hidden-comment prefix, which only pr-autofix
posts.

Wall-clock reset (issue #5477): the budget restarts on head SHA advance, a
reopen by a maintainer, or an operator reset (`--reset` or a
`/pr-autofix continue` comment). The signals are specified in
`github_core/round_cap.py`.

The pure logic (markers, reset detection, ACT/ESCALATE decision) lives in
`github_core/round_cap.py`; this script owns the `gh` I/O and the CLI.

Exit codes follow ADR-035, mirroring `check_pr_live_state.py`: 0 = round
recorded, under both caps (ACT); 1 = a cap is exceeded (ESCALATE);
2 = PR not found; 3 = external error (API failure); 4 = auth error.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from typing import Any, NoReturn

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plugin-root resolution: matches check_pr_live_state.py.
# ---------------------------------------------------------------------------
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
    RepoInfo,  # re-exported so tests can reach it via _mod.RepoInfo
    assert_gh_authenticated,
    resolve_repo_params,
    safe_log_str,
)
from github_core.output import (
    add_output_format_arg,
    write_skill_error,
    write_skill_output,
)
from github_core.round_cap import (
    ESCALATION_MARKER,
    MARKER_CLOSE,
    STATE_MARKER,
    Reset,
    detect_reset,
    escalation_already_posted,
    evaluate_round_cap,
    parse_marker,
    render_escalation_comment,
    render_state_marker,
    select_latest_state,
)

_SCRIPT_NAME = "check_pr_round_cap.py"
# Underscore aliases keep the names the tests and earlier callers import.
_STATE_MARKER = STATE_MARKER
_ESCALATION_MARKER = ESCALATION_MARKER
_MARKER_CLOSE = MARKER_CLOSE


class RoundCapStoreError(RuntimeError):
    """Marker-comment store failure. Mirrors the retired autofix lease's
    ``LeaseStoreError``: caught in ``main`` and reported through the same
    JSON-envelope error path ``check_pr_live_state.py`` uses.
    """


def _comment_endpoint(owner: str, repo: str, pr_number: int) -> str:
    return f"repos/{owner}/{repo}/issues/{pr_number}/comments"


def _run_gh_read(gh_args: list[str], what: str) -> str:
    """Run a read-only ``gh api`` call and return stdout. Raises RoundCapStoreError."""
    try:
        result = subprocess.run(
            ["gh", "api", *gh_args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise RoundCapStoreError(f"{what} failed: {exc}") from exc
    if result.returncode != 0:
        raise RoundCapStoreError(
            f"{what} exited {result.returncode}: "
            f"{safe_log_str((result.stderr or '')[:200])}"
        )
    return result.stdout or ""


def _list_comments(owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
    """Return PR issue comments (oldest first). Raises RoundCapStoreError.

    Does not reuse ``github_core.api.get_issue_comments``: it calls
    ``error_and_exit`` on failure (stderr, no JSON on stdout). A gate script
    needs every exit path to emit JSON so the caller's ``jq`` read never
    runs against empty input.
    """
    endpoint = _comment_endpoint(owner, repo, pr_number) + "?per_page=100"
    stdout = _run_gh_read(["--paginate", endpoint], "comment list")
    return _parse_paginated_json_arrays(stdout)


def _list_issue_events(owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
    """Return the PR's issue timeline events (oldest first). Raises RoundCapStoreError."""
    endpoint = f"repos/{owner}/{repo}/issues/{pr_number}/events?per_page=100"
    return _parse_paginated_json_arrays(_run_gh_read(["--paginate", endpoint], "event list"))


def _fetch_head_sha(owner: str, repo: str, pr_number: int) -> str:
    """Return the PR head commit SHA. Raises RoundCapStoreError."""
    endpoint = f"repos/{owner}/{repo}/pulls/{pr_number}"
    sha = _run_gh_read([endpoint, "--jq", ".head.sha"], "head sha read").strip()
    if not sha:
        raise RoundCapStoreError("head sha read returned empty output")
    return sha


_LOGIN_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_WRITE_PERMISSIONS = frozenset({"admin", "maintain", "write"})


def _actor_has_write_access(owner: str, repo: str, login: str) -> bool:
    """True when *login* has write access. Fails safe: any error means False.

    The login is validated against GitHub's username shape before it reaches
    the API path (CWE-22): a crafted value must not add path segments.
    """
    if not _LOGIN_PATTERN.match(login):
        return False
    endpoint = f"repos/{owner}/{repo}/collaborators/{login}/permission"
    try:
        permission = _run_gh_read([endpoint, "--jq", ".permission"], "permission read")
    except RoundCapStoreError as exc:
        logger.warning(
            "op=round_cap_permission_failed error=%s", safe_log_str(str(exc)),
        )
        return False
    return permission.strip() in _WRITE_PERMISSIONS


def _parse_paginated_json_arrays(raw_stdout: str) -> list[dict[str, Any]]:
    """Parse one or more JSON array documents from ``gh api --paginate``."""
    raw = raw_stdout.strip()
    if not raw:
        return []
    decoder = json.JSONDecoder()
    comments: list[dict[str, Any]] = []
    pos = 0
    while pos < len(raw):
        while pos < len(raw) and raw[pos].isspace():
            pos += 1
        if pos >= len(raw):
            break
        try:
            payload, pos = decoder.raw_decode(raw, pos)
        except json.JSONDecodeError as exc:
            raise RoundCapStoreError(f"comment list returned non-JSON: {exc}") from exc
        if not isinstance(payload, list):
            raise RoundCapStoreError("comment list returned non-list JSON payload")
        comments.extend(item for item in payload if isinstance(item, dict))
    return comments


def _post_comment(owner: str, repo: str, pr_number: int, body: str) -> None:
    """Post a new PR comment. Raises RoundCapStoreError on failure."""
    endpoint = _comment_endpoint(owner, repo, pr_number)
    try:
        result = subprocess.run(
            ["gh", "api", "--method", "POST", endpoint, "-f", f"body={body}"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise RoundCapStoreError(f"comment post failed: {exc}") from exc
    if result.returncode != 0:
        raise RoundCapStoreError(
            f"comment post exited {result.returncode}: "
            f"{safe_log_str((result.stderr or '')[:200])}"
        )


#: Defaults grounded in the evidence above: incidents ran 11-18 rounds over
#: multi-hour spans (46h wall clock for PR #1887) before a human intervened.
#: 5 rounds / 4 hours trips the breaker an order of magnitude below where
#: those incidents were still running, while leaving room for a normal
#: single-session CI-fix cycle (a handful of push/re-check rounds).
_DEFAULT_MAX_ROUNDS = 5
_DEFAULT_MAX_HOURS = 4.0


__all__ = [
    "RepoInfo",
    "Reset",
    "RoundCapStoreError",
    "build_parser",
    "detect_reset",
    "escalation_already_posted",
    "evaluate_round_cap",
    "main",
    "parse_marker",
    "render_escalation_comment",
    "render_state_marker",
    "select_latest_state",
]


# CLI below.


def _emit_error(
    message: str, code: int, error_type: str,
    output_format: str, pr_number: int, owner: str, repo: str,
) -> NoReturn:
    write_skill_error(
        message,
        code,
        error_type=error_type,
        output_format=output_format,
        script_name=_SCRIPT_NAME,
        extra={"pull_request": pr_number, "owner": owner, "repo": repo},
    )
    raise SystemExit(code)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Per-PR round/time circuit breaker for pr-autofix's T3/T4 "
            "thread-fix loop (issue #5056). Records one round and returns "
            "ACT when both the round-count and wall-clock caps hold, "
            "ESCALATE when either is exceeded."
        ),
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=int(os.environ.get("PR_AUTOFIX_MAX_ROUNDS", _DEFAULT_MAX_ROUNDS)),
        help=(
            "Round cap. Default: $PR_AUTOFIX_MAX_ROUNDS or "
            f"{_DEFAULT_MAX_ROUNDS} if unset."
        ),
    )
    parser.add_argument(
        "--max-hours",
        type=float,
        default=float(os.environ.get("PR_AUTOFIX_MAX_ROUND_HOURS", _DEFAULT_MAX_HOURS)),
        help=(
            "Wall-clock budget in hours since the first recorded round. "
            f"Default: $PR_AUTOFIX_MAX_ROUND_HOURS or {_DEFAULT_MAX_HOURS} if unset."
        ),
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Operator reset (issue #5477): restart the wall-clock budget and "
            "the round counter for this PR. Use after a human has decided the "
            "loop should continue."
        ),
    )
    add_output_format_arg(parser)
    return parser


def _optional_head_sha(owner: str, repo: str, pr_number: int) -> str | None:
    """Head SHA, or None on failure. A missing SHA only disables the SHA reset,
    which fails safe (no reset), so it must not block the gate."""
    try:
        return _fetch_head_sha(owner, repo, pr_number)
    except RoundCapStoreError as exc:
        logger.warning(
            "op=round_cap_head_sha_failed pr=%d error=%s", pr_number, safe_log_str(str(exc)),
        )
        return None


def _optional_events(
    owner: str, repo: str, pr_number: int,
    prior_state: dict[str, Any] | None, operator_flag: bool,
) -> list[dict[str, Any]]:
    """Timeline events for reopen detection. Skipped when no prior state or the
    operator flag already decides the reset; a fetch failure fails safe (no reset)."""
    if prior_state is None or operator_flag:
        return []
    try:
        return _list_issue_events(owner, repo, pr_number)
    except RoundCapStoreError as exc:
        logger.warning(
            "op=round_cap_events_failed pr=%d error=%s", pr_number, safe_log_str(str(exc)),
        )
        return []


def _post_escalation_note(
    owner: str, repo: str, pr_number: int,
    result: dict[str, Any], args: argparse.Namespace,
) -> bool:
    """Post the human-readable ESCALATE note. Non-fatal on failure: the state
    marker is already persisted and the ESCALATE verdict still fires."""
    body = render_escalation_comment(
        pr_number, result["round"], args.max_rounds,
        result["elapsed_hours"], args.max_hours, result["reason"],
        first_seen=result["state"]["first_seen"],
    )
    try:
        _post_comment(owner, repo, pr_number, body)
    except RoundCapStoreError as exc:
        logger.warning(
            "op=round_cap_escalation_note_failed pr=%d error=%s",
            pr_number, safe_log_str(str(exc)),
        )
        return False
    return True


def _load_comments_or_exit(
    owner: str, repo: str, pr_number: int, output_format: str, op_start: float,
) -> list[dict[str, Any]]:
    try:
        return _list_comments(owner, repo, pr_number)
    except RoundCapStoreError as exc:
        duration_ms = int((time.monotonic() - op_start) * 1000)
        logger.warning(
            "op=round_cap_failed pr=%d owner=%s repo=%s reason=comment_fetch_failed "
            "duration_ms=%d error=%s",
            pr_number, owner, repo, duration_ms, safe_log_str(str(exc)),
        )
        _emit_error(
            f"Failed to fetch PR comments: {exc}", 3, "ApiError",
            output_format, pr_number, owner, repo,
        )


def _persist_verdict(
    owner: str, repo: str, pr_number: int, comments: list[dict[str, Any]],
    prior_state: dict[str, Any] | None, result: dict[str, Any],
    args: argparse.Namespace, output_format: str,
) -> bool:
    """Post the state marker and, when missing, the human escalation note.

    Returns whether the escalation note was posted. A blocked call stays
    silent on the second and later attempts (issue #5477): with no reset, an
    ESCALATE whose state is already recorded as escalated, or already has a
    notice, writes no state marker. The notice is retried on its own when it
    is missing, so a failed notice post does not turn into marker spam.
    """
    escalating = result["action"] == "ESCALATE"
    reset = result["reset_reason"] is not None
    first_seen = result["state"]["first_seen"]
    noted = escalating and escalation_already_posted(
        comments, first_seen, allow_legacy=not reset,
    )
    recorded = escalating and (prior_state or {}).get("escalated") is True
    if not (escalating and not reset and (noted or recorded)):
        _post_state_marker(owner, repo, pr_number, result, output_format)
    if not escalating or noted:
        return False
    return _post_escalation_note(owner, repo, pr_number, result, args)


def _post_state_marker(
    owner: str, repo: str, pr_number: int, result: dict[str, Any], output_format: str,
) -> None:
    try:
        _post_comment(owner, repo, pr_number, render_state_marker(result["state"]))
    except RoundCapStoreError as exc:
        _emit_error(
            f"Failed to persist round-cap state comment: {exc}", 3, "ApiError",
            output_format, pr_number, owner, repo,
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_format = args.output_format
    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    pr_number = args.pull_request

    op_start = time.monotonic()
    comments = _load_comments_or_exit(owner, repo, pr_number, output_format, op_start)

    prior_state = select_latest_state(comments, _STATE_MARKER)
    now = datetime.now(UTC)
    head_sha = _optional_head_sha(owner, repo, pr_number)
    events = _optional_events(owner, repo, pr_number, prior_state, args.reset)
    reset = detect_reset(
        comments, events, args.reset,
        can_reopen_reset=lambda login: _actor_has_write_access(owner, repo, login),
    )
    result = evaluate_round_cap(
        prior_state, now, args.max_rounds, args.max_hours,
        head_sha=head_sha, reset=reset,
    )

    escalation_posted = _persist_verdict(
        owner, repo, pr_number, comments, prior_state, result, args, output_format,
    )

    output = {
        "pull_request": pr_number,
        "owner": owner,
        "repo": repo,
        "round": result["round"],
        "max_rounds": args.max_rounds,
        "elapsed_hours": result["elapsed_hours"],
        "max_hours": args.max_hours,
        "first_seen": result["state"]["first_seen"],
        "action": result["action"],
        "reason": result["reason"],
        "escalation_posted": escalation_posted,
        "reset_reason": result["reset_reason"],
    }

    duration_ms = int((time.monotonic() - op_start) * 1000)
    logger.info(
        "op=round_cap pr=%d owner=%s repo=%s round=%d action=%s duration_ms=%d",
        pr_number, owner, repo, result["round"], result["action"], duration_ms,
    )

    write_skill_output(
        output,
        output_format=output_format,
        human_summary=(
            f"PR #{pr_number} round-cap: {result['action']} ({result['reason']})"
        ),
        status="PASS" if result["action"] == "ACT" else "WARNING",
        script_name=_SCRIPT_NAME,
    )

    return 0 if result["action"] == "ACT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
