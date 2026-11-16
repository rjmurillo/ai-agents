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
              thread, and the branch is not BEHIND or DIRTY (default)
  green       required checks pass on the current head
  any-change  stop after the first poll that prints an event

Events
  head        a new commit landed on the PR branch
  check       a required check failed (one line per check)
  green       every required check passed on the current head
  comment     a new PR comment from someone other than the PR author or you
  review      a new review from someone else
  thread      a new review thread, or a reply in one, from someone else
  activity    more activity arrived than one poll can list; read every thread
  base        the base branch moved
  merge-state the branch became BEHIND or DIRTY
  merged      the PR merged
  closed      the PR closed without merging

Exit codes (ADR-035):
  0  the --until condition is met, or the PR merged
  1  the condition cannot be met without action: a required check failed, the
     branch is DIRTY, the PR closed, or (ready) unresolved threads or BEHIND
     block it after required checks pass
  2  bad arguments, or another pr_wait already watches this PR
  3  GitHub stayed unreachable for MAX_FAILED_POLLS consecutive polls

State lives in the user state directory under ``pr-babysit``. A lock makes a
second watcher for the same PR exit at once. A state file lets a restarted
watcher report what arrived while no watcher ran. The first run for a PR
records what already exists and reports only what comes after.
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
from typing import IO, Any

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

Json = dict[str, Any]

UNTIL_CHOICES = ("ready", "green", "any-change")
DEFAULT_INTERVAL = 30
MIN_INTERVAL = 10
MAX_BACKOFF = 300
MAX_FAILED_POLLS = 10
# A state file older than this describes an old session. Start a fresh
# baseline instead of replaying hours of comments as new events.
STALE_STATE_SECONDS = 6 * 3600
ACTIVITY_WINDOW = 50

SNAPSHOT_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  viewer { login }
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      url state headRefOid baseRefName baseRefOid mergeStateStatus
      author { login }
      comments(last: 50) { totalCount nodes { id url author { login } } }
      reviews(last: 50) { totalCount nodes { id url state author { login } } }
      reviewThreads(last: 50) {
        totalCount
        nodes {
          id
          comments(last: 1) { totalCount nodes { id url author { login } } }
        }
      }
    }
  }
}
"""

_PR_URL = re.compile(r"github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)")


@dataclass
class State:
    """What earlier polls already reported for one PR."""

    head: str = ""
    base_oid: str = ""
    merge_state: str = ""
    seen: set[str] = field(default_factory=set)
    thread_counts: dict[str, int] = field(default_factory=dict)
    totals: dict[str, int] = field(default_factory=dict)
    failing: set[str] = field(default_factory=set)
    green_head: str = ""

    def to_json(self) -> Json:
        return {
            "head": self.head,
            "base_oid": self.base_oid,
            "merge_state": self.merge_state,
            "seen": sorted(self.seen),
            "thread_counts": self.thread_counts,
            "totals": self.totals,
            "failing": sorted(self.failing),
            "green_head": self.green_head,
        }

    @classmethod
    def from_json(cls, data: Json) -> State:
        return cls(
            head=str(data.get("head", "")),
            base_oid=str(data.get("base_oid", "")),
            merge_state=str(data.get("merge_state", "")),
            seen=set(data.get("seen", [])),
            thread_counts={str(k): int(v) for k, v in data.get("thread_counts", {}).items()},
            totals={str(k): int(v) for k, v in data.get("totals", {}).items()},
            failing=set(data.get("failing", [])),
            green_head=str(data.get("green_head", "")),
        )


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


def state_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "pr-babysit"


def acquire_lock(path: Path) -> IO[str] | None:
    """Take a non-blocking exclusive lock. Return None when another holds it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+", encoding="utf-8")  # held for the process life; closed on refusal
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def load_state(path: Path, now: float) -> State | None:
    """Return the saved state, or None for a fresh baseline."""
    try:
        if now - path.stat().st_mtime > STALE_STATE_SECONDS:
            return None
        return State.from_json(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def save_state(path: Path, state: State) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state.to_json()), encoding="utf-8")
    os.replace(tmp, path)


def _login(node: Json | None) -> str:
    author = (node or {}).get("author") or {}
    return str(author.get("login") or "ghost")


def _short(sha: str) -> str:
    return sha[:7] if sha else "unknown"


def diff_activity(state: State, pr: Json, viewer: str, baseline: bool) -> list[str]:
    """Return activity events and update state. A baseline poll prints nothing."""
    events: list[str] = []
    ignored = {_login(pr).lower(), viewer.lower()}

    def note(kind: str, node: Json, detail: str = "") -> None:
        node_id = str(node.get("id", ""))
        if not node_id or node_id in state.seen:
            return
        state.seen.add(node_id)
        login = _login(node)
        if baseline or login.lower() in ignored:
            return
        suffix = f" {detail}" if detail else ""
        events.append(f"{kind}: {login}{suffix} {node.get('url', '')}".rstrip())

    overflow = False
    for key, kind in (("comments", "comment"), ("reviews", "review")):
        conn = pr.get(key) or {}
        nodes = conn.get("nodes") or []
        total = int(conn.get("totalCount") or 0)
        before = state.totals.get(key, total)
        if total - before > len(nodes):
            overflow = True
        state.totals[key] = total
        for node in nodes:
            note(kind, node, str(node.get("state", "")) if kind == "review" else "")

    threads = pr.get("reviewThreads") or {}
    thread_total = int(threads.get("totalCount") or 0)
    if thread_total - state.totals.get("reviewThreads", thread_total) > len(
        threads.get("nodes") or []
    ):
        overflow = True
    state.totals["reviewThreads"] = thread_total
    for thread in threads.get("nodes") or []:
        thread_id = str(thread.get("id", ""))
        conn = thread.get("comments") or {}
        count = int(conn.get("totalCount") or 0)
        previous = state.thread_counts.get(thread_id)
        state.thread_counts[thread_id] = count
        if previous is not None and count - previous > 1:
            overflow = True
        for node in conn.get("nodes") or []:
            note("thread", node)

    if overflow and not baseline:
        events.append("activity: more arrived than one poll lists; read every thread")
    return events


def diff_pr(state: State, pr: Json, baseline: bool) -> tuple[list[str], int | None]:
    """Return head, base, merge-state, and terminal events plus an exit code."""
    events: list[str] = []
    pr_state = str(pr.get("state", ""))
    if pr_state == "MERGED":
        return ["merged"], 0
    if pr_state == "CLOSED":
        return ["closed"], 1

    head = str(pr.get("headRefOid", ""))
    if state.head and head != state.head:
        events.append(f"head: {_short(head)}")
        state.failing.clear()
        state.green_head = ""
    state.head = head

    base_oid = str(pr.get("baseRefOid", ""))
    if state.base_oid and base_oid != state.base_oid and not baseline:
        events.append(f"base: {pr.get('baseRefName', '')} moved to {_short(base_oid)}")
    state.base_oid = base_oid

    merge_state = str(pr.get("mergeStateStatus", ""))
    if merge_state in ("BEHIND", "DIRTY") and merge_state != state.merge_state:
        events.append(f"merge-state: {merge_state}")
    state.merge_state = merge_state
    if merge_state == "DIRTY":
        return events, 1
    return events, None


def evaluate_gate(state: State, gate: Json, until: str) -> tuple[list[str], int | None]:
    """Turn a why_pr_blocked payload into check events and an exit decision."""
    events: list[str] = []
    failing = set(gate.get("FailingRequired") or [])
    for name in sorted(failing - state.failing):
        events.append(f"check: {name} failed on {_short(state.head)}")
    state.failing = failing

    waiting = (
        gate.get("PendingRequired")
        or gate.get("MissingRequired")
        or gate.get("IndeterminateRequired")
    )
    if not gate.get("RulesetContextsAvailable", True):
        waiting = waiting or gate.get("OverallState") != "SUCCESS"
    green = not failing and not waiting
    if green and state.green_head != state.head:
        events.append(f"green: required checks passed on {_short(state.head)}")
        state.green_head = state.head

    if failing:
        return events, 1
    if until == "green":
        return events, 0 if green else None
    if until == "ready" and green:
        if int(gate.get("UnresolvedThreads") or 0) > 0:
            return events, 1
        if state.merge_state == "BEHIND":
            return events, 1
        if state.merge_state in ("CLEAN", "HAS_HOOKS", "UNSTABLE", "BLOCKED"):
            return events, 0
    return events, None


def fetch_snapshot(owner: str, name: str, number: int) -> tuple[Json, str]:
    from github_core.api import gh_graphql

    data = gh_graphql(SNAPSHOT_QUERY, {"owner": owner, "name": name, "number": number})
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
    if result.returncode not in (0, 1):
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise RuntimeError(f"why_pr_blocked exit {result.returncode}: {detail[-1:] or ''}")
    payload = json.loads(result.stdout)
    data = payload.get("Data")
    if not isinstance(data, dict):
        raise RuntimeError("why_pr_blocked returned no Data payload")
    return data


def poll_once(
    state: State, target: tuple[str, str, int], until: str, baseline: bool
) -> tuple[list[str], int | None]:
    """Read one snapshot and, unless the PR is already terminal, the merge gate."""
    pr, viewer = fetch_snapshot(*target)
    events, code = diff_pr(state, pr, baseline)
    events += diff_activity(state, pr, viewer, baseline)
    if code is None:
        gate_events, code = evaluate_gate(state, fetch_gate(*target), until)
        events += gate_events
    return events, code


def emit(lines: list[str]) -> None:
    for line in lines:
        print(line, flush=True)


def run(args: argparse.Namespace) -> int:
    try:
        owner, name, number = parse_target(args.pr, args.repo)
    except ValueError as exc:
        log(str(exc))
        return 2

    key = f"{owner}__{name}__{number}".replace("/", "_")
    directory = state_dir()
    lock = acquire_lock(directory / f"{key}.lock")
    if lock is None:
        log(f"another pr_wait already watches {owner}/{name}#{number}; not starting a second one")
        return 2

    state_path = directory / f"{key}.json"
    saved = load_state(state_path, time.time())
    state = saved or State()
    baseline = saved is None
    failures = 0
    delay = max(args.interval, MIN_INTERVAL)

    while True:
        try:
            events, code = poll_once(state, (owner, name, number), args.until, baseline)
        except LookupError as exc:
            log(str(exc))
            return 2
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
        save_state(state_path, state)
        emit(events)
        baseline = False
        if code is not None:
            return code
        if args.until == "any-change" and events:
            return 0
        time.sleep(delay)


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
