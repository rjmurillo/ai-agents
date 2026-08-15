#!/usr/bin/env python3
"""Per-PR round/time circuit breaker for pr-autofix's T3/T4 thread loop (issue #5056).

pr-autofix's thread-lifecycle loop (Phase 2, T3/T4 in
`src/copilot-cli/skills/pr-autofix/SKILL.md`) had no machine-enforced cap on
how many fix/review rounds it runs against one PR. The lease and live-state
gate protect against racing or acting on a stale PR; neither bounds how long
the loop keeps acting on a PR that is still live and actionable. Evidence:
`.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md` (PR #1887:
46h wall clock, 69 commits, 11+ bot review rounds) and
`.agents/governance/CI-FEEDBACK-SUBLOOP.md` line 11 (PRs #1965 and #1979,
18 rounds each). Prose caps have been written down and ignored repeatedly.
This script follows `check_pr_live_state.py`'s shape (issue #2455): a
machine-checked JSON envelope pr-autofix branches on, not another sentence
in a SKILL.md.

Storage decision (Search Before Building, Layer 1): `pr_autofix_lease.py`
(ADR-076) already solved "small per-PR state that survives a session
restart" with a hidden-marker PR comment instead of counting commits or
writing a file. This script reuses that shape:

    1. A squash-merge, rebase, or force-push (all routine in this repo's
       pr-autofix flow) destroys commit history a counter would replay; a
       PR comment survives all three because it lives on the issue
       timeline, not the ref graph.
    2. Commit counting needs a git checkout and a commit-naming convention;
       a comment marker needs only the GitHub API, matching
       `check_pr_live_state.py`'s read-path design.
    3. A fourth ad-hoc storage scheme repeats the failure
       `.claude/rules/push-lock.md` documents for lock files (three
       incompatible schemes coexisting silently). Reuse avoids a second.

Unlike the lease, this marker carries no security weight: a forged or
duplicated marker at worst causes a premature ESCALATE (fail-safe), never a
bypassed cap (fail-open, the failure this script prevents). So it skips the
lease's verified-comment-author bookkeeping and trusts the latest marker
carrying this script's own hidden-comment prefix, which only pr-autofix
posts.

Exit codes follow ADR-035, mirroring `check_pr_live_state.py`: 0 = round
recorded, under both caps (ACT); 1 = a cap is exceeded (ESCALATE);
2 = PR not found; 3 = external error (API failure); 4 = auth error.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from typing import Any, NoReturn

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plugin-root resolution: matches check_pr_live_state.py and pr_autofix_lease.py.
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

_SCRIPT_NAME = "check_pr_round_cap.py"


class RoundCapStoreError(RuntimeError):
    """Marker-comment store failure. Mirrors ``pr_autofix_lease.py``'s
    ``LeaseStoreError``: caught in ``main`` and reported through the same
    JSON-envelope error path ``check_pr_live_state.py`` uses.
    """


def _comment_endpoint(owner: str, repo: str, pr_number: int) -> str:
    return f"repos/{owner}/{repo}/issues/{pr_number}/comments"


def _list_comments(owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
    """Return PR issue comments (oldest first). Raises RoundCapStoreError.

    Does not reuse ``github_core.api.get_issue_comments``: it calls
    ``error_and_exit`` on failure (stderr, no JSON on stdout). A gate script
    needs every exit path to emit JSON so the caller's ``jq`` read never
    runs against empty input.
    """
    endpoint = _comment_endpoint(owner, repo, pr_number) + "?per_page=100"
    try:
        result = subprocess.run(
            ["gh", "api", "--paginate", endpoint],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise RoundCapStoreError(f"comment list failed: {exc}") from exc
    if result.returncode != 0:
        raise RoundCapStoreError(
            f"comment list exited {result.returncode}: "
            f"{safe_log_str((result.stderr or '')[:200])}"
        )
    return _parse_paginated_json_arrays(result.stdout or "")


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

#: Hidden marker prefix that makes every round-cap state comment findable in
#: one timeline scan, matching pr_autofix_lease.py's marker-comment pattern.
_STATE_MARKER = "<!-- pr-autofix-round-cap-state:"
#: Separate marker for the human-readable escalation notice, so a repeat
#: `record` call after ESCALATE does not repost the same notice (issue #5056
#: task item 4: leave a note, not spam one per re-invocation).
_ESCALATION_MARKER = "<!-- pr-autofix-round-cap-escalated:"
_MARKER_CLOSE = "-->"

#: Defaults grounded in the evidence above: incidents ran 11-18 rounds over
#: multi-hour spans (46h wall clock for PR #1887) before a human intervened.
#: 5 rounds / 4 hours trips the breaker an order of magnitude below where
#: those incidents were still running, while leaving room for a normal
#: single-session CI-fix cycle (a handful of push/re-check rounds).
_DEFAULT_MAX_ROUNDS = 5
_DEFAULT_MAX_HOURS = 4.0

__all__ = [
    "RepoInfo",
    "RoundCapStoreError",
    "build_parser",
    "evaluate_round_cap",
    "main",
    "parse_marker",
    "render_escalation_comment",
    "render_state_marker",
    "select_latest_state",
]


# Marker parsing / rendering below: pure functions, unit-tested directly.


def parse_marker(body: str, prefix: str) -> dict[str, Any] | None:
    """Extract the JSON payload from a hidden marker comment, or None.

    Tolerates a missing close token or malformed JSON by returning None
    rather than raising: a corrupted marker must never crash the gate, it
    must be treated as "no prior state" so the breaker still fails safe.
    """
    start = body.find(prefix)
    if start == -1:
        return None
    payload_start = start + len(prefix)
    end = body.find(_MARKER_CLOSE, payload_start)
    if end == -1:
        return None
    raw = body[payload_start:end].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def select_latest_state(
    comments: list[dict[str, Any]], prefix: str,
) -> dict[str, Any] | None:
    """Return the most recent marker payload matching *prefix*, or None.

    GitHub's issue-comments endpoint returns comments in ascending
    chronological order, so the latest matching marker is the last one
    found scanning forward. Bounded to the newest 100 comments so a PR
    with a very long history cannot turn this into an unbounded scan
    (same defensive bound as pr_autofix_lease.py's MAX_SCAN).
    """
    latest: dict[str, Any] | None = None
    for comment in comments[-100:]:
        body = comment.get("body") or ""
        parsed = parse_marker(body, prefix)
        if parsed is not None:
            latest = parsed
    return latest


def render_state_marker(state: dict[str, Any]) -> str:
    """Render round-cap state as a hidden marker comment body."""
    payload = json.dumps(state, separators=(",", ":"), sort_keys=True)
    return (
        f"{_STATE_MARKER}{payload}{_MARKER_CLOSE}\n"
        f"pr-autofix round-cap: round {state['round']} recorded "
        f"(first seen {state['first_seen']})."
    )


def render_escalation_comment(
    pr_number: int,
    round_count: int,
    max_rounds: int,
    elapsed_hours: float,
    max_hours: float,
    reason: str,
) -> str:
    """Render the human-readable ESCALATE notice pr-autofix posts once."""
    payload = json.dumps({"round": round_count}, separators=(",", ":"))
    return (
        f"{_ESCALATION_MARKER}{payload}{_MARKER_CLOSE}\n"
        f"**pr-autofix round-cap breaker tripped for #{pr_number}.**\n\n"
        f"{reason}\n\n"
        f"- Rounds recorded: {round_count} (cap: {max_rounds})\n"
        f"- Wall clock since first round: {elapsed_hours:.1f}h (cap: {max_hours:.1f}h)\n\n"
        "pr-autofix is stopping automated work on this PR. A human needs to "
        "review the remaining thread(s)/CI failure(s) directly, or restart "
        "the counter by editing/removing the round-cap state marker."
    )


# Evaluation below: pure function, unit-tested directly.


def evaluate_round_cap(
    prior_state: dict[str, Any] | None,
    now: datetime,
    max_rounds: int,
    max_hours: float,
) -> dict[str, Any]:
    """Advance round-cap state by one round and classify ACT vs ESCALATE.

    Returns the new state dict (to persist) plus the verdict fields
    (action, reason, round, elapsed_hours). Exceeding either the round
    count or the wall-clock budget escalates; the checks are independent,
    matching task requirement 3 ("wall-clock budget exceeded independent
    of round count").
    """
    if prior_state and isinstance(prior_state.get("first_seen"), str):
        first_seen_raw = prior_state["first_seen"]
        prior_round = prior_state.get("round", 0)
        round_count = (prior_round if isinstance(prior_round, int) else 0) + 1
    else:
        first_seen_raw = now.isoformat()
        round_count = 1

    try:
        first_seen = datetime.fromisoformat(first_seen_raw)
    except ValueError:
        # A corrupted timestamp must not crash the gate; restart the clock
        # rather than fail open on an unparseable value.
        first_seen = now
        first_seen_raw = now.isoformat()

    elapsed_hours = max((now - first_seen).total_seconds() / 3600.0, 0.0)

    if round_count >= max_rounds:
        action = "ESCALATE"
        reason = f"round cap reached: {round_count} rounds recorded (cap: {max_rounds})"
    elif elapsed_hours >= max_hours:
        action = "ESCALATE"
        reason = (
            f"wall-clock budget exceeded: {elapsed_hours:.1f}h since first round "
            f"(cap: {max_hours:.1f}h)"
        )
    else:
        action = "ACT"
        reason = f"round {round_count}/{max_rounds} under cap ({elapsed_hours:.1f}h/{max_hours:.1f}h)"

    new_state = {
        "round": round_count,
        "first_seen": first_seen_raw,
        "last_round_at": now.isoformat(),
    }
    return {
        "state": new_state,
        "action": action,
        "reason": reason,
        "round": round_count,
        "elapsed_hours": round(elapsed_hours, 2),
    }


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
    add_output_format_arg(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_format = args.output_format
    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    pr_number = args.pull_request

    op_start = time.monotonic()
    try:
        comments = _list_comments(owner, repo, pr_number)
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

    prior_state = select_latest_state(comments, _STATE_MARKER)
    now = datetime.now(UTC)
    result = evaluate_round_cap(prior_state, now, args.max_rounds, args.max_hours)

    marker_body = render_state_marker(result["state"])
    try:
        _post_comment(owner, repo, pr_number, marker_body)
    except RoundCapStoreError as exc:
        _emit_error(
            f"Failed to persist round-cap state comment: {exc}", 3, "ApiError",
            output_format, pr_number, owner, repo,
        )

    escalation_posted = False
    if result["action"] == "ESCALATE":
        already_escalated = select_latest_state(
            comments, _ESCALATION_MARKER,
        )
        if already_escalated is None:
            escalation_body = render_escalation_comment(
                pr_number, result["round"], args.max_rounds,
                result["elapsed_hours"], args.max_hours, result["reason"],
            )
            try:
                _post_comment(owner, repo, pr_number, escalation_body)
                escalation_posted = True
            except RoundCapStoreError as exc:
                # Non-fatal: the round-cap state is already persisted above
                # and the ESCALATE verdict below still fires. Losing the
                # human-readable note is degraded, not broken.
                logger.warning(
                    "op=round_cap_escalation_note_failed pr=%d error=%s",
                    pr_number, safe_log_str(str(exc)),
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
