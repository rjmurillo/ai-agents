#!/usr/bin/env python3
"""Watch one pull request and print one line per real event.

Usage:
    pr_wait.py <pr> [--repo owner/name] [--until ready|green|any-change]
               [--interval SECONDS]

<pr> is a PR number or a PR URL. Without --repo, the repository comes from the
URL or from the current checkout. Stdout carries only events, one line each, so
a host monitor (for example Claude Code's Monitor tool) wakes the agent once
per real event. Progress and transient errors go to stderr.

The script composes existing project-toolkit pieces instead of a second
GitHub client. Each poll runs one small GraphQL snapshot through
``github_core.api.gh_graphql`` (PR state, head, base, merge state, activity)
and the github skill's ``why_pr_blocked.py`` for the merge gate (required
checks from the base-branch ruleset, plus unresolved threads).

--until
  ready       required checks pass on the current head, no unresolved review
              thread, and the branch is not BEHIND, DIRTY, or a draft (default)
  green       required checks pass on the current head
  any-change  stop after the first poll that prints an event

Events: head, check (a required check failed), green, comment, review,
thread, activity (more arrived than one poll lists), base, merge-state
(BEHIND or DIRTY), blocked (always precedes exit 1), merged, closed.
Comments, reviews, and threads by the PR author or by you are skipped.

Exit codes (ADR-035):
  0  the --until condition is met, or the PR merged
  1  a new blocker needs action: a required check failed, the branch is DIRTY,
     the PR closed, or (ready) unresolved threads, BEHIND, or draft block it
     after required checks pass. A blocker already reported to an earlier run
     does not exit again; the watcher keeps waiting for it to clear.
  2  bad arguments, the PR does not exist, or another pr_wait already watches
     this PR
  3  GitHub stayed unreachable for MAX_FAILED_POLLS consecutive polls
  4  gh is not authenticated

State lives in the user state directory under ``pr-babysit``. A lock makes a
second watcher for the same PR exit at once. A state file lets a watcher
restarted within STALE_STATE_SECONDS report what arrived while none ran.
A first run, or a run after a longer gap, records the existing comments,
reviews, and threads and reports only newer ones. It reports the current
check and merge state at once.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from pr_wait_activity import diff_activity  # noqa: E402 - needs the script directory
from pr_wait_state import (  # noqa: E402 - needs the script directory on sys.path
    Json,
    State,
    acquire_lock,
    load_state,
    save_state,
    state_dir,
    state_key,
)

UNTIL_CHOICES = ("ready", "green", "any-change")
DEFAULT_INTERVAL = 30
MIN_INTERVAL = 10
MAX_BACKOFF = 300
MAX_FAILED_POLLS = 10
READY_MERGE_STATES = ("CLEAN", "HAS_HOOKS", "UNSTABLE", "BLOCKED")
# Review bots post 30 to 120 seconds after a push. A zero-thread reading
# taken sooner is not evidence that no thread is coming.
SETTLE_SECONDS = 180
_NOT_FOUND = re.compile(r"Could not resolve to a (PullRequest|Repository)|NOT_FOUND")

SNAPSHOT_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  viewer { login }
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      url state isDraft reviewDecision headRefOid baseRefName baseRefOid mergeStateStatus
      author { login }
      comments(last: 50) { totalCount nodes { id url author { login } } }
      reviews(last: 50) { totalCount nodes { id url state author { login } } }
      reviewThreads(last: 100) {
        totalCount
        nodes {
          id
          first: comments(first: 1) { nodes { id url author { login } } }
          last: comments(last: 1) { totalCount nodes { id url author { login } } }
        }
      }
    }
  }
}
"""

_PR_URL = re.compile(r"github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)")


class AuthError(RuntimeError):
    """gh has no usable credential; retrying cannot help."""


@dataclass
class Poll:
    """One poll's output: events to print, blockers seen, and a terminal exit."""

    events: list[str] = field(default_factory=list)
    blockers: set[str] = field(default_factory=set)
    done: int | None = None
    review_pending: bool = False


def log(message: str) -> None:
    print(f"pr_wait: {message}", file=sys.stderr, flush=True)


def parse_target(raw: str, repo: str | None) -> tuple[str, str, int]:
    """Return (owner, name, number) from a PR number or URL plus --repo."""
    match = _PR_URL.search(raw)
    if match:
        owner, name, number = match.group(1), match.group(2), int(match.group(3))
        if repo and repo.lower() != f"{owner}/{name}".lower():
            raise ValueError(f"--repo {repo} does not match the PR URL {owner}/{name}")
        return owner, name, number
    if not raw.isdigit() or int(raw) <= 0:
        raise ValueError(f"not a PR number or PR URL: {raw!r}")
    if repo:
        parts = repo.split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError(f"--repo must be owner/name, got {repo!r}")
        return parts[0], parts[1], int(raw)
    from github_core.api import resolve_repo_params

    info = resolve_repo_params("", "")
    return info.owner, info.repo, int(raw)


def _short(sha: str) -> str:
    return sha[:7] if sha else "unknown"


def diff_pr(state: State, pr: Json, baseline: bool) -> Poll:
    """Return head, base, merge-state, and terminal events plus blockers."""
    poll = Poll()
    pr_state = str(pr.get("state", ""))
    if pr_state == "MERGED":
        return Poll(events=["merged"], done=0)
    if pr_state == "CLOSED":
        return Poll(events=["closed"], blockers={"closed"}, done=1)

    head = str(pr.get("headRefOid", ""))
    if state.head and head != state.head:
        poll.events.append(f"head: {_short(head)}")
        state.failing.clear()
        state.green_head = ""
        state.blockers.clear()
    state.head = head

    base_oid = str(pr.get("baseRefOid", ""))
    if state.base_oid and base_oid != state.base_oid and not baseline:
        poll.events.append(f"base: {pr.get('baseRefName', '')} moved to {_short(base_oid)}")
    state.base_oid = base_oid

    merge_state = str(pr.get("mergeStateStatus", ""))
    if merge_state in ("BEHIND", "DIRTY") and merge_state != state.merge_state:
        poll.events.append(f"merge-state: {merge_state}")
    state.merge_state = merge_state
    if merge_state == "DIRTY":
        poll.blockers.add(f"dirty:{_short(head)}:{_short(base_oid)}")
    if pr.get("isDraft"):
        poll.blockers.add("draft")
    decision = pr.get("reviewDecision")
    if decision == "CHANGES_REQUESTED":
        poll.blockers.add(f"changes-requested:{_short(head)}")
    poll.review_pending = decision == "REVIEW_REQUIRED"
    return poll


def evaluate_gate(state: State, gate: Json, until: str, poll: Poll) -> None:
    """Add check events, blockers, and a ready exit from a why_pr_blocked payload."""
    failing = set(gate.get("FailingRequired") or [])
    for name in sorted(failing - state.failing):
        poll.events.append(f"check: {name} failed on {_short(state.head)}")
    state.failing = failing
    poll.blockers.update(f"check:{name}" for name in failing)

    waiting = bool(
        gate.get("PendingRequired")
        or gate.get("MissingRequired")
        or gate.get("IndeterminateRequired")
    )
    if not gate.get("RulesetContextsAvailable", True):
        waiting = waiting or gate.get("OverallState") != "SUCCESS"
    green = not failing and not waiting
    if green and state.green_head != state.head:
        poll.events.append(f"green: required checks passed on {_short(state.head)}")
        state.green_head = state.head

    if until == "green":
        poll.blockers = {b for b in poll.blockers if b.startswith(("check:", "dirty:"))}
        poll.done = 0 if green else None
    elif until == "ready":
        _ready_verdict(state, gate, poll, green)


def _ready_verdict(state: State, gate: Json, poll: Poll, green: bool) -> None:
    """Draft, threads, and BEHIND block ready only once required checks pass."""
    if not green:
        poll.blockers = {b for b in poll.blockers if b.startswith(("check:", "dirty:"))}
        return
    if int(gate.get("UnresolvedThreads") or 0) > 0:
        poll.blockers.add("threads")
    if state.merge_state == "BEHIND":
        poll.blockers.add(f"behind:{_short(state.base_oid)}")
    settled = _seconds_since(gate.get("HeadCommittedAt")) >= SETTLE_SECONDS
    if (
        not poll.blockers
        and not poll.review_pending
        and settled
        and state.merge_state in READY_MERGE_STATES
    ):
        poll.done = 0


def _seconds_since(stamp: object) -> float:
    """Seconds since an ISO-8601 UTC stamp; an unreadable stamp counts as settled."""
    from datetime import datetime

    try:
        moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return float(SETTLE_SECONDS)
    return time.time() - moment.timestamp()


def fetch_snapshot(owner: str, name: str, number: int) -> tuple[Json, str]:
    from github_core.api import gh_graphql, is_auth_failure_text

    try:
        data = gh_graphql(SNAPSHOT_QUERY, {"owner": owner, "name": name, "number": number})
    except RuntimeError as exc:
        if _NOT_FOUND.search(str(exc)):
            raise LookupError(f"PR {owner}/{name}#{number} not found") from exc
        if is_auth_failure_text(str(exc)):
            raise AuthError(str(exc)) from exc
        raise
    pr = ((data.get("repository") or {}).get("pullRequest")) or None
    if pr is None:
        raise LookupError(f"PR {owner}/{name}#{number} not found")
    viewer = str((data.get("viewer") or {}).get("login") or "")
    return pr, viewer


def why_pr_blocked_path() -> Path:
    if _plugin_root:
        candidate = (
            Path(_plugin_root) / "skills" / "github" / "scripts" / "pr" / "why_pr_blocked.py"
        )
        if candidate.is_file():
            return candidate
    return Path(__file__).resolve().parents[2] / "github" / "scripts" / "pr" / "why_pr_blocked.py"


def fetch_gate(owner: str, name: str, number: int) -> Json:
    """Run why_pr_blocked.py and return its Data payload."""
    result = subprocess.run(
        [
            sys.executable,
            str(why_pr_blocked_path()),
            "--owner",
            owner,
            "--repo",
            name,
            "--pull-request",
            str(number),
            "--output-format",
            "json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    detail = (result.stderr or result.stdout).strip().splitlines()
    last = detail[-1] if detail else ""
    if result.returncode == 2:
        raise LookupError(f"why_pr_blocked: {last}")
    if result.returncode == 4:
        raise AuthError(f"why_pr_blocked: {last}")
    if result.returncode not in (0, 1):
        raise RuntimeError(f"why_pr_blocked exit {result.returncode}: {last}")
    payload = json.loads(result.stdout)
    data = payload.get("Data")
    if not isinstance(data, dict):
        raise RuntimeError("why_pr_blocked returned no Data payload")
    return data


def poll_once(state: State, target: tuple[str, str, int], until: str, baseline: bool) -> Poll:
    """Read one snapshot and, unless the PR is already terminal, the merge gate."""
    pr, viewer = fetch_snapshot(*target)
    poll = diff_pr(state, pr, baseline)
    poll.events += diff_activity(state, pr, viewer, baseline)
    if poll.done is None:
        evaluate_gate(state, fetch_gate(*target), until, poll)
    return poll


def settle(state: State, poll: Poll, until: str) -> int | None:
    """Turn a poll into an exit code. A blocker exits only the first time it is seen."""
    if poll.done is not None and not poll.blockers:
        state.blockers.clear()
        return poll.done
    if "closed" in poll.blockers:
        return 1
    if until == "any-change":
        return 0 if poll.events else None
    new = poll.blockers - state.blockers
    state.blockers = set(poll.blockers)
    if new:
        poll.events.append(f"blocked: {', '.join(sorted(new))}")
        return 1
    return poll.done


def emit(lines: list[str]) -> None:
    for line in lines:
        print(line, flush=True)


def watch(state: State, state_path: Path, target: tuple[str, str, int], args: Any) -> int:
    baseline = not state_path.exists() or not state.head
    failures = 0
    delay = max(args.interval, MIN_INTERVAL)
    while True:
        try:
            poll = poll_once(state, target, args.until, baseline)
        except LookupError as exc:
            log(str(exc))
            return 2
        except AuthError as exc:
            log(f"gh is not authenticated: {str(exc)[:200]}")
            return 4
        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
            failures += 1
            text = str(exc)
            log(f"poll failed ({failures}/{MAX_FAILED_POLLS}): {text[:200]}")
            if failures >= MAX_FAILED_POLLS:
                print("unreachable: GitHub stayed unreachable; check the rate limit", flush=True)
                return 3
            if "rate limit" in text.lower():
                delay = min(delay * 2, MAX_BACKOFF)
            time.sleep(delay)
            continue

        failures = 0
        delay = max(args.interval, MIN_INTERVAL)
        code = settle(state, poll, args.until)
        save_state(state_path, state)
        emit(poll.events)
        baseline = False
        if code is not None:
            return code
        time.sleep(delay)


def run(args: argparse.Namespace) -> int:
    try:
        owner, name, number = parse_target(args.pr, args.repo)
    except ValueError as exc:
        log(str(exc))
        return 2

    key = state_key(owner, name, number)
    directory = state_dir()
    lock = acquire_lock(directory / f"{key}.lock")
    if lock is None:
        log(f"another pr_wait already watches {owner}/{name}#{number}; not starting a second one")
        return 2
    with lock:
        state_path = directory / f"{key}.json"
        saved = load_state(state_path, time.time())
        if saved is None:
            state_path.unlink(missing_ok=True)
        return watch(saved or State(), state_path, (owner, name, number), args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Watch one pull request and print one line per real event.",
    )
    parser.add_argument("pr", help="PR number or PR URL")
    parser.add_argument("--repo", default=None, help="owner/name; default from URL or checkout")
    parser.add_argument("--until", choices=UNTIL_CHOICES, default="ready")
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Seconds between polls (default {DEFAULT_INTERVAL}, floor {MIN_INTERVAL})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
