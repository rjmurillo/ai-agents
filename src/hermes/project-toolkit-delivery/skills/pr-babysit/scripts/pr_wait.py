#!/usr/bin/env python3
"""Watch one pull request and print one line per real event.

Usage:
    pr_wait.py <pr> [--repo owner/name] [--until ready|green|any-change]
               [--interval SECONDS]

The PR can be a number or URL. The repo defaults to the URL or current checkout.
Stdout carries events. Stderr carries progress and transient faults.
Polls read a GraphQL snapshot and the ``why_pr_blocked.py`` merge gate.
The interval uses ``gh event listen`` when available and sleeps otherwise.

--until ready (default) requires green checks, no unresolved threads,
and a branch that is current, clean, and not a draft. ``green`` only checks CI.
``any-change`` also stops at the first poll that emits an event.
Activity from the PR author or current viewer is skipped.

Exit codes (ADR-035):
  0  the --until condition is met, or the PR merged
  1  a new blocker needs action: a required check failed or never reported,
     the branch is DIRTY, the PR closed, or (ready) unresolved threads,
     BEHIND, draft, a required review, or a changes-requested review block it
     after required checks pass. A ready exit waits SETTLE_SECONDS after this
     watcher first saw the head, so review bots can post. A blocker already
     reported does not exit again; the watcher waits for it to clear.
  2  bad arguments, another pr_wait already watches this PR, gh is not on
     PATH, or why_pr_blocked.py failed with a config error or returned a
     payload missing a key
  3  GitHub stayed unreachable for MAX_FAILED_POLLS consecutive polls (stdout
     line starts with ``unreachable:``), or the PR does not exist (stdout line
     starts with ``not found:``). A missing PR exits at once and is never
     retried; do not retry it.
  4  gh is not authenticated

A per-PR lock and state file live under ``pr-babysit`` in user state.
A restart within STALE_STATE_SECONDS resumes; otherwise it records a new baseline.
The first poll always reports current check and merge state.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import random
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

# Bound as a module and read at call time, so a test that patches github_core.api applies.
import github_core.api as gh_api  # noqa: E402 - needs the lib directory on sys.path
from pr_wait_activity import diff_activity, review_blockers  # noqa: E402 - needs the script directory
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
# Review bots post 30 to 120 seconds after a push (observed for Copilot and
# Devin; see the github skill's wait_for_unresolved_zero.py). A zero-thread
# reading taken sooner is not evidence that no thread is coming. Heuristic.
SETTLE_SECONDS = 180
# Blockers that still apply under --until green; the rest gate ready only.
GREEN_BLOCKERS = ("check:", "dirty:", "absent:")
# Same grace why_pr_blocked gives a required check that has not reported.
ABSENT_GRACE_SECONDS = 2700
# Keys pr_wait reads from why_pr_blocked.py. A missing key is a contract break,
# not a pass, so the poll fails loud instead of reading the PR as green.
GATE_KEYS = (
    "FailingRequired",
    "PendingRequired",
    "MissingRequired",
    "AbsentRequired",
    "IndeterminateRequired",
    "UnresolvedThreads",
    "RulesetContextsAvailable",
    "OverallState",
)
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
          id isResolved isOutdated
          first: comments(first: 1) { nodes { id url author { login } } }
          last: comments(last: 1) { totalCount nodes { id url author { login } } }
        }
      }
    }
  }
}
"""

# GitHub names. An owner is letters, digits, and '-', starting alphanumeric.
# A repository is letters, digits, '.', '_', '-', and may start with '.'
# (".github"), but '.' and '..' are not names. The names also key the state
# and lock files, so nothing else may pass.
_OWNER = r"[A-Za-z0-9][A-Za-z0-9-]*"
_REPO = r"(?!\.\.?(?:/|$))[A-Za-z0-9._-]+"
_PR_URL = re.compile(rf"github\.com/({_OWNER})/({_REPO})/pull/(\d+)")
_REPO_ARG = re.compile(rf"({_OWNER})/({_REPO})")


class AuthError(RuntimeError):
    """gh has no usable credential; retrying cannot help."""


class ContractError(RuntimeError):
    """why_pr_blocked.py returned a payload without a key pr_wait reads."""


class SetupError(RuntimeError):
    """The gh CLI is not installed or not on PATH; retrying cannot help."""


@dataclass
class Poll:
    """One poll's output: events to print, blockers seen, and a terminal exit."""

    events: list[str] = field(default_factory=list)
    blockers: set[str] = field(default_factory=set)
    done: int | None = None
    # True once ready-only blockers were evaluated on a green head this poll.
    ready_checked: bool = False
    # Unresolved, current review thread ids in the snapshot window.
    open_threads: set[str] = field(default_factory=set)


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
        arg = _REPO_ARG.fullmatch(repo)
        if arg is None or arg.group(2) in (".", ".."):
            raise ValueError(f"--repo must be owner/name, got {repo!r}")
        return arg.group(1), arg.group(2), int(raw)
    info = gh_api.resolve_repo_params("", "")
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
        # Check failures are per head. Review and thread blockers persist
        # until a green poll shows them cleared, so a push does not re-arm them.
        state.blockers = {b for b in state.blockers if not b.startswith("check:")}
    if head != state.head or not state.head_seen_at:
        state.head_seen_at = time.time()
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
    poll.blockers.update(review_blockers(pr, head))
    poll.open_threads = {
        str(t.get("id"))
        for t in ((pr.get("reviewThreads") or {}).get("nodes") or [])
        if t.get("id") and not t.get("isResolved") and not t.get("isOutdated")
    }
    return poll


def evaluate_gate(state: State, gate: Json, until: str, poll: Poll) -> None:
    """Add check events, blockers, and a ready exit from a why_pr_blocked payload."""
    missing = [key for key in GATE_KEYS if key not in gate]
    if missing:
        raise ContractError(f"why_pr_blocked payload lacks {', '.join(missing)}")
    failing = set(gate.get("FailingRequired") or [])
    for name in sorted(failing - state.failing):
        poll.events.append(f"check: {name} failed on {_short(state.head)}")
    state.failing = failing
    poll.blockers.update(f"check:{name}" for name in failing)
    absent = sorted(gate.get("AbsentRequired") or [])
    # why_pr_blocked ages a missing check from the commit date, not the push,
    # so trust "absent" only once this watcher has seen the head that long.
    if absent and time.time() - state.head_seen_at >= ABSENT_GRACE_SECONDS:
        poll.blockers.add(f"absent:{','.join(absent)}:{_short(state.head)}")

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
    elif not green:
        # A rerun can turn the same head red, then green again; report each recovery.
        state.green_head = ""

    if until == "green":
        poll.blockers = {b for b in poll.blockers if b.startswith(GREEN_BLOCKERS)}
        poll.done = 0 if green and not poll.blockers else None
    else:
        _ready_verdict(state, gate, poll, green)


def _ready_verdict(state: State, gate: Json, poll: Poll, green: bool) -> None:
    """Draft, threads, and BEHIND block ready only once required checks pass."""
    if not green:
        poll.blockers = {b for b in poll.blockers if b.startswith(GREEN_BLOCKERS)}
        return
    poll.ready_checked = True
    unresolved = int(gate.get("UnresolvedThreads") or 0)
    if unresolved > 0:
        # One blocker per thread: a new thread fires once, a resolved one just
        # drops, and threads waiting on a reviewer stay quiet across pushes.
        poll.blockers.update(f"thread:{tid}" for tid in poll.open_threads)
        if unresolved > len(poll.open_threads):
            poll.blockers.add("threads:unlisted")
    if state.merge_state == "BEHIND":
        poll.blockers.add(f"behind:{_short(state.base_oid)}")
    # Commit age is not push age: a slow pre-push makes a fresh push look old.
    # Settle on when this watcher first saw the head instead.
    settled = time.time() - state.head_seen_at >= SETTLE_SECONDS
    if not poll.blockers and settled and state.merge_state in READY_MERGE_STATES:
        poll.events.append(f"ready: {_short(state.head)} can merge once the merge gate agrees")
        poll.done = 0


def fetch_snapshot(owner: str, name: str, number: int) -> tuple[Json, str]:
    try:
        data = gh_api.gh_graphql(SNAPSHOT_QUERY, {"owner": owner, "name": name, "number": number})
    except FileNotFoundError as exc:
        raise SetupError(f"gh is not installed or not on PATH: {exc}") from exc
    except RuntimeError as exc:
        if _NOT_FOUND.search(str(exc)):
            raise LookupError(f"PR {owner}/{name}#{number} not found") from exc
        if gh_api.is_auth_failure_text(str(exc)):
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


def _is_not_found_envelope(stdout: str) -> bool:
    """Distinguish a missing PR from a retryable exit 3."""
    try:
        payload = json.loads(stdout)
    except ValueError:
        return False
    error = payload.get("Error") if isinstance(payload, dict) else None
    return isinstance(error, dict) and error.get("Type") == "NotFound"


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
    if result.returncode == 3 and _is_not_found_envelope(result.stdout):
        raise LookupError(f"PR {owner}/{name}#{number} not found")
    if result.returncode == 2:
        raise SetupError(f"why_pr_blocked config error: {last}")
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
    new = poll.blockers - state.blockers
    if poll.ready_checked:
        state.blockers = set(poll.blockers)
    else:
        # Ready-only blockers were not evaluated (checks pending, or green
        # mode). Keep them known so they do not fire again later.
        kept = {b for b in state.blockers if not b.startswith(GREEN_BLOCKERS)}
        state.blockers = set(poll.blockers) | kept
    if new:
        poll.events.append(f"blocked: {', '.join(sorted(new))}")
        return 1
    if until == "any-change" and poll.events:
        return 0
    return poll.done


def emit(lines: list[str]) -> None:
    for line in lines:
        print(line, flush=True)


def watch(state: State, state_path: Path, target: tuple[str, str, int], args: Any) -> int:
    baseline = not state_path.exists() or not state.head
    failures = 0
    delay = max(args.interval, MIN_INTERVAL)
    while True:
        before = copy.deepcopy(state)
        try:
            poll = poll_once(state, target, args.until, baseline)
        except LookupError as exc:
            log(str(exc))
            print(f"not found: {str(exc)[:200]}", flush=True)
            return 3
        except (ContractError, SetupError) as exc:
            log(str(exc))
            return 2
        except AuthError as exc:
            log(f"gh is not authenticated: {str(exc)[:200]}")
            return 4
        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
            # A failed poll must not consume what it already diffed.
            state = before
            failures += 1
            text = str(exc)
            log(f"poll failed ({failures}/{MAX_FAILED_POLLS}): {text[:200]}")
            if failures >= MAX_FAILED_POLLS:
                print("unreachable: GitHub stayed unreachable; check the rate limit", flush=True)
                return 3
            delay = min(delay * 2, MAX_BACKOFF)
            time.sleep(delay + random.uniform(0, delay / 4))
            continue

        failures = 0
        delay = max(args.interval, MIN_INTERVAL)
        code = settle(state, poll, args.until)
        # Print before saving: a crash in between repeats an event, never drops one.
        emit(poll.events)
        save_state(state_path, state)
        baseline = False
        if code is not None:
            return code
        gh_api.wait_for_pr_event(
            gh_api.pr_url(*target), gh_api.ALL_PR_EVENTS, delay, min_seconds=MIN_INTERVAL
        )


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
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
