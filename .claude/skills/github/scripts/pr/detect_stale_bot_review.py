#!/usr/bin/env python3
"""Detect a stale bot CHANGES_REQUESTED review that blocks merge (issue #5950).

After every thread is fixed and resolved and CI is green, a PR can stay blocked
because a bot (CodeRabbit, Copilot) left a ``CHANGES_REQUESTED`` review on an
older commit. A later bot pass posts ``COMMENTED``, which does not supersede it.
Only an ``APPROVED`` review or a dismissal clears it, and dismissal is a human
action. This script classifies that state and emits the handoff text. It never
dismisses a review and never posts a comment.

It reads three sibling scripts: ``get_pr_context.py`` (head SHA, merge state,
unresolved thread count), ``get_pr_checks.py`` (CI verdict), and
``get_pr_reviews.py`` (review id, state, commit).

Verdicts in ``Data.verdict``:

    NO_BOT_CHANGES_REQUESTED  No bot holds an active CHANGES_REQUESTED review.
    NOT_READY                 A bot holds one, but a thread is unresolved, CI is
                              not green, or the branch needs an update first.
                              Finish that work; this is not a stale-review case.
    FRESH_CHANGES_REQUESTED   A bot review on the current head still requests
                              changes. Address its findings.
    REQUEST_REREVIEW          Stale review, PR ready, no re-review at head yet.
                              Request one fresh bot review, then run this again.
    DISMISSAL_HANDOFF         Stale review, PR ready, and the bot already
                              re-reviewed head (or has no known trigger). Hand
                              ``Data.handoff`` to a human to dismiss.

A bot re-review that posts ``COMMENTED`` at head leaves the old review active,
so it moves the verdict to DISMISSAL_HANDOFF. An ``APPROVED`` review at head
supersedes the old one and the bot drops out of the active list.

The repeated re-review rounds that a bot starts on every push are the fixed
point ``check_pr_round_cap.py`` already bounds. See the pr-autofix skill.

Exit codes follow ADR-035:
    0 - Classified (read ``Data.verdict``)
    1 - Invalid parameters / logic error
    2 - Not found or config error
    3 - External error (API failure, unreadable sibling output)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
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
    assert_gh_authenticated,
    resolve_repo_params,
)
from github_core.bot_config import is_bot
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

_SCRIPT = "detect_stale_bot_review.py"
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Review states that move GitHub's reviewDecision. COMMENTED and PENDING do not.
_VERDICT_STATES = frozenset({"APPROVED", "CHANGES_REQUESTED", "DISMISSED"})

# Merge states where the branch itself needs work before a review matters.
_BRANCH_WORK_STATES = frozenset({"BEHIND", "DIRTY"})

# Comment that makes a known bot re-review the current head. A bot absent from
# this map has no verified trigger, so the script never invents one.
_REREVIEW_TRIGGERS: dict[str, str] = {
    "coderabbitai[bot]": "@coderabbitai review",
}

_DISMISS_MESSAGE = (
    "Every review thread is resolved with a fix commit and CI is green. "
    "This review predates those commits."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect a stale bot CHANGES_REQUESTED review that blocks merge.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="Pull request number")
    add_output_format_arg(parser)
    return parser


def _author_key(review: dict[str, Any]) -> str:
    return str(review.get("author_canonical") or review.get("author") or "")


def _author_login(review: dict[str, Any]) -> str:
    return str(review.get("author_observed") or review.get("author") or "")


def _review_order(review: dict[str, Any]) -> tuple[str, int]:
    review_id = review.get("id")
    return str(review.get("submittedAt") or ""), review_id if isinstance(review_id, int) else 0


def _latest_verdict_by_author(reviews: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return each author's latest verdict-bearing review, keyed by canonical login."""
    latest: dict[str, dict[str, Any]] = {}
    for review in sorted(reviews, key=_review_order):
        if review.get("state") in _VERDICT_STATES and _author_key(review):
            latest[_author_key(review)] = review
    return latest


def _reviewed_head_after(
    reviews: list[dict[str, Any]], blocking: dict[str, Any], head_sha: str
) -> bool:
    """True when the blocking review's author posted a later review at head."""
    key = _author_key(blocking)
    return any(
        _author_key(r) == key
        and r.get("commit_id") == head_sha
        and _review_order(r) > _review_order(blocking)
        for r in reviews
    )


def _active_bot_blockers(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest = _latest_verdict_by_author(reviews)
    return [
        r
        for r in latest.values()
        if r.get("state") == "CHANGES_REQUESTED" and is_bot(_author_login(r))
    ]


def _human_blockers(reviews: list[dict[str, Any]]) -> list[str]:
    latest = _latest_verdict_by_author(reviews)
    return sorted(
        _author_login(r)
        for r in latest.values()
        if r.get("state") == "CHANGES_REQUESTED" and not is_bot(_author_login(r))
    )


def _readiness_reasons(pr: dict[str, Any], ci_green: bool) -> list[str]:
    """Reasons the PR is not yet in the all-threads-resolved, CI-green state."""
    reasons: list[str] = []
    unresolved = pr.get("review_thread_unresolved_count")
    if pr.get("review_thread_counts_complete") is not True or not isinstance(unresolved, int):
        reasons.append("review thread count is incomplete")
    elif unresolved > 0:
        reasons.append(f"{unresolved} review thread(s) unresolved")
    if not ci_green:
        reasons.append("CI is not passing")
    state = pr.get("merge_state_status")
    if state in _BRANCH_WORK_STATES:
        reasons.append(f"merge state is {state}")
    return reasons


def build_dismissal_command(owner: str, repo: str, pr: int, review_id: object) -> str:
    return (
        f"gh api -X PUT repos/{owner}/{repo}/pulls/{pr}/reviews/{review_id}/dismissals "
        f'-f event=DISMISS -f message="{_DISMISS_MESSAGE}"'
    )


def _bot_entry(
    review: dict[str, Any],
    reviews: list[dict[str, Any]],
    head_sha: str,
) -> dict[str, Any]:
    login = _author_login(review)
    trigger = _REREVIEW_TRIGGERS.get(_author_key(review))
    if review.get("commit_id") == head_sha:
        action = "FRESH_CHANGES_REQUESTED"
    elif trigger and not _reviewed_head_after(reviews, review, head_sha):
        action = "REQUEST_REREVIEW"
    else:
        action = "DISMISSAL_HANDOFF"
    return {
        "login": login,
        "review_id": review.get("id"),
        "commit_id": review.get("commit_id"),
        "url": review.get("url"),
        "action": action,
        "rereview_trigger": trigger,
    }


def _aggregate(bots: list[dict[str, Any]]) -> str:
    actions = {b["action"] for b in bots}
    for verdict in ("FRESH_CHANGES_REQUESTED", "REQUEST_REREVIEW"):
        if verdict in actions:
            return verdict
    return "DISMISSAL_HANDOFF"


def build_handoff(
    owner: str,
    repo: str,
    pr: int,
    head_sha: str,
    bots: list[dict[str, Any]],
    human_blockers: list[str],
) -> str:
    """Return the ready-to-run text a human needs to dismiss the stale reviews."""
    lines = [
        f"PR #{pr} is blocked by stale bot CHANGES_REQUESTED review(s). Head is {head_sha}.",
        "Safe to dismiss: every review thread is resolved and CI is green. "
        "The review predates the fix commits.",
        "The agent does not dismiss reviews. A human runs:",
    ]
    for bot in bots:
        lines.append(f"- {bot['login']} review {bot['review_id']} on commit {bot['commit_id']}:")
        lines.append(f"  {build_dismissal_command(owner, repo, pr, bot['review_id'])}")
    if human_blockers:
        lines.append(
            "A human CHANGES_REQUESTED review also stands ("
            + ", ".join(human_blockers)
            + "). Dismissing the bot review alone will not unblock the merge."
        )
    return "\n".join(lines)


def classify(
    *,
    owner: str,
    repo: str,
    pr_number: int,
    pr: dict[str, Any],
    ci_green: bool,
    reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    """Classify the PR's bot CHANGES_REQUESTED state. Pure: no I/O."""
    head_sha = str(pr.get("head_sha") or "")
    blockers = _active_bot_blockers(reviews)
    data: dict[str, Any] = {
        "pull_request": pr_number,
        "owner": owner,
        "repo": repo,
        "head_sha": head_sha,
        "verdict": "NO_BOT_CHANGES_REQUESTED",
        "bots": [],
        "reasons": [],
        "human_changes_requested": _human_blockers(reviews),
        "handoff": None,
    }
    if not blockers:
        return data
    data["bots"] = [_bot_entry(r, reviews, head_sha) for r in blockers]
    reasons = _readiness_reasons(pr, ci_green)
    if not head_sha:
        reasons.append("head SHA is unknown")
    if reasons:
        data["verdict"] = "NOT_READY"
        data["reasons"] = reasons
        return data
    data["verdict"] = _aggregate(data["bots"])
    if data["verdict"] == "DISMISSAL_HANDOFF":
        stale = [b for b in data["bots"] if b["action"] == "DISMISSAL_HANDOFF"]
        data["handoff"] = build_handoff(
            owner, repo, pr_number, head_sha, stale, data["human_changes_requested"]
        )
    return data


def _run_sibling(script: str, args: list[str]) -> tuple[int, dict[str, Any] | None]:
    """Run a sibling skill script with JSON output. Return (exit code, Data or None)."""
    result = subprocess.run(
        [sys.executable, os.path.join(_SCRIPT_DIR, script), *args, "--output-format", "json"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.returncode, None
    data = envelope.get("Data") if isinstance(envelope, dict) else None
    return result.returncode, data if isinstance(data, dict) else None


def _common_args(owner: str, repo: str, pr: int) -> list[str]:
    return ["--owner", owner, "--repo", repo, "--pull-request", str(pr)]


def _fetch_inputs(
    owner: str, repo: str, pr: int
) -> tuple[dict[str, Any], bool, list[dict[str, Any]]]:
    """Fetch PR context, CI verdict, and reviews. Raises RuntimeError on failure."""
    args = _common_args(owner, repo, pr)
    code, context = _run_sibling("get_pr_context.py", args)
    if code != 0 or context is None:
        raise RuntimeError(f"get_pr_context.py failed for PR #{pr} (exit {code})")
    # get_pr_checks.py exits 1 on failing checks and 7 on incomplete data but
    # still prints its verdict, so only an unreadable result is an error.
    _, checks = _run_sibling("get_pr_checks.py", args)
    if checks is None:
        raise RuntimeError(f"get_pr_checks.py returned no verdict for PR #{pr}")
    code, review_data = _run_sibling("get_pr_reviews.py", args)
    reviews = review_data.get("reviews") if review_data else None
    if code != 0 or not isinstance(reviews, list):
        raise RuntimeError(f"get_pr_reviews.py failed for PR #{pr} (exit {code})")
    return context, checks.get("AllPassing") is True, reviews


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)
    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo, pr = resolved.owner, resolved.repo, args.pull_request

    try:
        context, ci_green, reviews = _fetch_inputs(owner, repo, pr)
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        write_skill_error(
            str(exc) or "sibling script timed out",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name=_SCRIPT,
            extra={"pull_request": pr},
        )
        return 3

    data = classify(
        owner=owner,
        repo=repo,
        pr_number=pr,
        pr=context,
        ci_green=ci_green,
        reviews=reviews,
    )
    write_skill_output(
        data,
        output_format=fmt,
        human_summary=f"PR #{pr}: {data['verdict']}",
        status="PASS",
        script_name=_SCRIPT,
    )
    if fmt == "human" and data["handoff"]:
        print(data["handoff"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
