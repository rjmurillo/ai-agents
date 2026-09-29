"""Pure round-cap logic for pr-autofix's breaker (issues #5056, #5477).

Marker parsing and rendering, reset-signal detection, and the ACT/ESCALATE
decision. No I/O: `check_pr_round_cap.py` owns the `gh` calls and the CLI, and
re-exports these names so its tests and callers keep one import path.
See that script's docstring for the storage and reset design.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

#: Hidden marker prefix that makes every round-cap state comment findable in
#: one timeline scan, using the same marker-comment pattern.
STATE_MARKER = "<!-- pr-autofix-round-cap-state:"
#: Separate marker for the human-readable escalation notice, so a repeat
#: `record` call after ESCALATE does not repost the same notice (issue #5056
#: task item 4: leave a note, not spam one per re-invocation).
ESCALATION_MARKER = "<!-- pr-autofix-round-cap-escalated:"
MARKER_CLOSE = "-->"

#: Comment authors whose ``/pr-autofix continue`` line counts as an operator
#: reset. GitHub's ``author_association`` values that imply repo access. MEMBER is
#: excluded: it covers every org member, including read-only ones.
_RESET_ASSOCIATIONS = frozenset({"OWNER", "COLLABORATOR"})
_RESET_COMMAND = re.compile(r"(?mi)^[ \t]*/pr-autofix[ \t]+continue[ \t]*$")


@dataclass(frozen=True, slots=True)
class Reset:
    """A signal that restarts the wall-clock budget.

    ``restart_rounds`` is True only for an explicit operator reset. Automatic
    signals (head advance, reopen) leave the round counter alone.
    """

    reason: str
    restart_rounds: bool = False




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
    end = body.find(MARKER_CLOSE, payload_start)
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
        payload = parse_marker(comment.get("body") or "", ESCALATION_MARKER)
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
    latest = _latest_marker_comment(comments, STATE_MARKER)
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
        f"{STATE_MARKER}{payload}{MARKER_CLOSE}\n"
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
        f"{ESCALATION_MARKER}{payload}{MARKER_CLOSE}\n"
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

