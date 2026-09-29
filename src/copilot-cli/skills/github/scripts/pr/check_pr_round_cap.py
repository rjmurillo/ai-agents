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

Storage decision (Search Before Building, Layer 1): the retired autofix lease
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

Wall-clock reset (issue #5477). The budget measures time the loop has been
working, not calendar age, so it restarts on these signals (the round counter
keeps its semantics except under the explicit operator reset):

    1. Head SHA advance: the PR head differs from the SHA stored with the
       prior state, so the prior rounds' work landed. Clock restarts only.
    2. Reopen: a non-bot ``reopened`` timeline event newer than the latest
       state marker. Clock restarts only.
    3. Operator reset, either ``--reset`` or a ``/pr-autofix continue`` line in
       a comment from an OWNER or COLLABORATOR newer than the latest
       state marker. Clock and round counter both restart.

Plain comments do not reset: reviewers and bots comment constantly, so a
generic comment signal would keep a runaway loop alive. A forged reset needs
write access and at worst grants more rounds, never a silent bypass.

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
from dataclasses import dataclass
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

_SCRIPT_NAME = "check_pr_round_cap.py"


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
#: one timeline scan, using the same marker-comment pattern.
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

#: Comment authors whose ``/pr-autofix continue`` line counts as an operator
#: reset. GitHub's ``author_association`` values that imply repo access. MEMBER is
#: excluded: it covers every org member, including read-only ones.
_RESET_ASSOCIATIONS = frozenset({"OWNER", "COLLABORATOR"})
_RESET_COMMAND = re.compile(r"(?mi)^[ \t]*/pr-autofix[ \t]+continue[ \t]*$")

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


@dataclass(frozen=True, slots=True)
class Reset:
    """A signal that restarts the wall-clock budget.

    ``restart_rounds`` is True only for an explicit operator reset. Automatic
    signals (head advance, reopen) leave the round counter alone.
    """

    reason: str
    restart_rounds: bool = False


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
    (same defensive bound the retired autofix lease used for MAX_SCAN).
    """
    found = _latest_marker_comment(comments, prefix)
    return found[1] if found else None


def _latest_marker_comment(
    comments: list[dict[str, Any]], prefix: str,
) -> tuple[int, dict[str, Any]] | None:
    """Return (index into *comments*, payload) of the newest matching marker."""
    start = max(len(comments) - 100, 0)
    latest: tuple[int, dict[str, Any]] | None = None
    for offset, comment in enumerate(comments[start:]):
        parsed = parse_marker(comment.get("body") or "", prefix)
        if parsed is not None:
            latest = (start + offset, parsed)
    return latest


def escalation_already_posted(
    comments: list[dict[str, Any]], first_seen: str,
) -> bool:
    """True when an escalation notice already exists for this state.

    A notice is for the same state when its payload ``first_seen`` equals the
    current one, so a reset (new ``first_seen``) earns a fresh notice. A
    legacy notice without ``first_seen`` (posted before issue #5477) matches
    any state, which keeps the old post-once behavior for those PRs.
    """
    for comment in comments[-100:]:
        payload = parse_marker(comment.get("body") or "", _ESCALATION_MARKER)
        if payload is None:
            continue
        recorded = payload.get("first_seen")
        if recorded is None or recorded == first_seen:
            return True
    return False


def detect_reset(
    comments: list[dict[str, Any]],
    events: list[dict[str, Any]],
    operator_flag: bool,
) -> Reset | None:
    """Return the strongest reset signal newer than the latest state marker.

    Order: operator reset (flag or ``/pr-autofix continue`` comment) beats a
    reopen because it also restarts the round counter. Only signals newer than
    the latest state marker count, so a consumed signal cannot fire twice.
    """
    if operator_flag:
        return Reset("operator flag --reset", restart_rounds=True)
    latest = _latest_marker_comment(comments, _STATE_MARKER)
    if latest is None:
        return None
    index, _ = latest
    for comment in comments[index + 1:]:
        if _is_operator_continue(comment):
            return Reset("operator comment /pr-autofix continue", restart_rounds=True)
    marker_time = comments[index].get("created_at")
    if isinstance(marker_time, str) and _reopened_after(events, marker_time):
        return Reset("human reopen")
    return None


def _is_operator_continue(comment: dict[str, Any]) -> bool:
    user = comment.get("user") or {}
    if user.get("type") == "Bot":
        return False
    if comment.get("author_association") not in _RESET_ASSOCIATIONS:
        return False
    return bool(_RESET_COMMAND.search(comment.get("body") or ""))


def _reopened_after(events: list[dict[str, Any]], marker_time: str) -> bool:
    for event in events:
        if event.get("event") != "reopened":
            continue
        actor = event.get("actor") or {}
        created = event.get("created_at")
        if actor.get("type") == "Bot" or not isinstance(created, str):
            continue
        if created > marker_time:  # same-format UTC ISO 8601 strings sort chronologically
            return True
    return False


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
    first_seen: str | None = None,
) -> str:
    """Render the human-readable ESCALATE notice pr-autofix posts once per state."""
    fields: dict[str, Any] = {"round": round_count}
    if first_seen is not None:
        fields["first_seen"] = first_seen
    payload = json.dumps(fields, separators=(",", ":"), sort_keys=True)
    return (
        f"{_ESCALATION_MARKER}{payload}{_MARKER_CLOSE}\n"
        f"**pr-autofix round-cap breaker tripped for #{pr_number}.**\n\n"
        f"{reason}\n\n"
        f"- Rounds recorded: {round_count} (cap: {max_rounds})\n"
        f"- Wall clock since first round: {elapsed_hours:.1f}h (cap: {max_hours:.1f}h)\n\n"
        "pr-autofix is stopping automated work on this PR. A human needs to "
        "review the remaining thread(s)/CI failure(s) directly. To resume the "
        "loop, push a new commit, reopen the PR (restarts the wall-clock "
        "budget), or comment `/pr-autofix continue` as a maintainer (restarts "
        "the wall-clock budget and the round counter)."
    )


# Evaluation below: pure function, unit-tested directly.


def evaluate_round_cap(
    prior_state: dict[str, Any] | None,
    now: datetime,
    max_rounds: int,
    max_hours: float,
    head_sha: str | None = None,
    reset: Reset | None = None,
) -> dict[str, Any]:
    """Advance round-cap state by one round and classify ACT vs ESCALATE.

    Returns the new state dict (to persist) plus the verdict fields
    (action, reason, round, elapsed_hours, reset_reason). Exceeding either
    the round count or the wall-clock budget escalates; the checks are
    independent, matching task requirement 3 ("wall-clock budget exceeded
    independent of round count").

    The wall-clock anchor ``first_seen`` restarts when *reset* is given or when
    *head_sha* differs from the SHA stored with the prior state (issue #5477).
    A prior state without a stored SHA never counts as an advance.
    """
    first_seen_raw, first_seen, round_count = _carry_forward(prior_state, now)

    stored_sha = _stored_head_sha(prior_state)
    reset_reason: str | None = None
    if reset is not None:
        reset_reason = reset.reason
        if reset.restart_rounds:
            round_count = 1
    elif head_sha and stored_sha and head_sha != stored_sha:
        reset_reason = "head sha advanced"
    if reset_reason is not None:
        first_seen = now
        first_seen_raw = now.isoformat()

    elapsed_hours = max((now - first_seen).total_seconds() / 3600.0, 0.0)

    action, reason = _classify(round_count, elapsed_hours, max_rounds, max_hours)

    new_state: dict[str, Any] = {
        "round": round_count,
        "first_seen": first_seen_raw,
        "last_round_at": now.isoformat(),
    }
    recorded_sha = head_sha or stored_sha
    if recorded_sha:
        new_state["head_sha"] = recorded_sha
    return {
        "state": new_state,
        "action": action,
        "reason": reason,
        "round": round_count,
        "elapsed_hours": round(elapsed_hours, 2),
        "reset_reason": reset_reason,
    }


def _carry_forward(
    prior_state: dict[str, Any] | None, now: datetime,
) -> tuple[str, datetime, int]:
    """Return (first_seen ISO string, first_seen, round count) for this call."""
    if prior_state and isinstance(prior_state.get("first_seen"), str):
        first_seen_raw = prior_state["first_seen"]
        prior_round = prior_state.get("round", 0)
        round_count = (prior_round if isinstance(prior_round, int) else 0) + 1
    else:
        first_seen_raw = now.isoformat()
        round_count = 1
    try:
        return first_seen_raw, datetime.fromisoformat(first_seen_raw), round_count
    except ValueError:
        # A corrupted timestamp must not crash the gate; restart the clock
        # rather than fail open on an unparseable value.
        return now.isoformat(), now, round_count


def _classify(
    round_count: int, elapsed_hours: float, max_rounds: int, max_hours: float,
) -> tuple[str, str]:
    """Return (action, reason). Round cap and wall-clock arm are independent."""
    if round_count >= max_rounds:
        return "ESCALATE", f"round cap reached: {round_count} rounds recorded (cap: {max_rounds})"
    if elapsed_hours >= max_hours:
        return "ESCALATE", (
            f"wall-clock budget exceeded: {elapsed_hours:.1f}h since first round "
            f"(cap: {max_hours:.1f}h)"
        )
    return "ACT", (
        f"round {round_count}/{max_rounds} under cap ({elapsed_hours:.1f}h/{max_hours:.1f}h)"
    )


def _stored_head_sha(prior_state: dict[str, Any] | None) -> str | None:
    sha = (prior_state or {}).get("head_sha")
    return sha if isinstance(sha, str) and sha else None


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
    result: dict[str, Any], args: argparse.Namespace, output_format: str,
) -> bool:
    """Post the state marker and, on a fresh ESCALATE, the human note.

    Returns whether the escalation note was posted. A blocked call stays silent
    on the second and later attempts: when the verdict is ESCALATE and this
    state already has an escalation notice, another state marker only grows
    the timeline (issue #5477).
    """
    escalating = result["action"] == "ESCALATE"
    noted = escalating and escalation_already_posted(comments, result["state"]["first_seen"])
    if noted and result["reset_reason"] is None:
        return False
    try:
        _post_comment(owner, repo, pr_number, render_state_marker(result["state"]))
    except RoundCapStoreError as exc:
        _emit_error(
            f"Failed to persist round-cap state comment: {exc}", 3, "ApiError",
            output_format, pr_number, owner, repo,
        )
    if not escalating or noted:
        return False
    return _post_escalation_note(owner, repo, pr_number, result, args)


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
    reset = detect_reset(comments, events, args.reset)
    result = evaluate_round_cap(
        prior_state, now, args.max_rounds, args.max_hours,
        head_sha=head_sha, reset=reset,
    )

    escalation_posted = _persist_verdict(
        owner, repo, pr_number, comments, result, args, output_format,
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
