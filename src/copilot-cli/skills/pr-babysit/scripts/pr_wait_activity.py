"""Comment, review, and thread diffing for pr_wait.py.

Each poll reads the newest comments, reviews, and review threads. An id seen
before is skipped, and so is a post by the PR author or the viewer. When more
arrived than one poll lists, an ``activity`` line tells the agent to read
every thread.
"""

from __future__ import annotations

from pr_wait_state import Json, State

THREAD_WINDOW = 100


def _login(node: Json | None) -> str:
    author = (node or {}).get("author") or {}
    return str(author.get("login") or "ghost")


def _nodes(conn: Json | None) -> list[Json]:
    return list((conn or {}).get("nodes") or [])


def _total(conn: Json | None) -> int:
    return int((conn or {}).get("totalCount") or 0)


class _Notes:
    """Collects activity events, skipping seen ids and the author's own posts."""

    def __init__(self, state: State, ignored: set[str], baseline: bool) -> None:
        self._state = state
        self._ignored = ignored
        self._baseline = baseline
        self._events: list[str] = []
        self._overflow = False

    def mark_overflow(self) -> None:
        self._overflow = True

    def note(self, kind: str, node: Json, detail: str = "") -> None:
        node_id = str(node.get("id", ""))
        if not node_id or node_id in self._state.seen:
            return
        self._state.seen.add(node_id)
        login = _login(node)
        if self._baseline or login.lower() in self._ignored:
            return
        suffix = f" {detail}" if detail else ""
        self._events.append(f"{kind}: {login}{suffix} {node.get('url', '')}".rstrip())

    def connection(self, key: str, conn: Json | None, kind: str) -> None:
        total = _total(conn)
        nodes = _nodes(conn)
        if total - self._state.totals.get(key, total) > len(nodes):
            self._overflow = True
        self._state.totals[key] = total
        for node in nodes:
            self.note(kind, node, str(node.get("state", "")) if kind == "review" else "")

    def thread(self, thread: Json) -> None:
        thread_id = str(thread.get("id", ""))
        last = thread.get("last") or {}
        count = _total(last)
        previous = self._state.thread_counts.get(thread_id)
        self._state.thread_counts[thread_id] = count
        # A gap between the first and last comment means replies this poll
        # cannot list: more than one new reply, or a new thread with replies.
        if (previous is None and count > 2) or (previous is not None and count - previous > 1):
            self._overflow = True
        for node in _nodes(thread.get("first")) + _nodes(last):
            self.note("thread", node)

    def finish(self, thread_total: int) -> list[str]:
        """Return the events, plus one activity line when a poll missed some."""
        if self._baseline:
            if thread_total > THREAD_WINDOW:
                self._events.append(
                    f"activity: {thread_total} threads; replies in the oldest "
                    f"{thread_total - THREAD_WINDOW} are not watched; read every thread"
                )
        elif self._overflow:
            self._events.append("activity: more arrived than one poll lists; read every thread")
        return self._events


def diff_activity(state: State, pr: Json, viewer: str, baseline: bool) -> list[str]:
    """Return activity events and update state. A baseline poll prints nothing."""
    notes = _Notes(state, {_login(pr).lower(), viewer.lower()}, baseline)
    notes.connection("comments", pr.get("comments"), "comment")
    notes.connection("reviews", pr.get("reviews"), "review")

    threads = pr.get("reviewThreads") or {}
    thread_total = _total(threads)
    if thread_total - state.totals.get("reviewThreads", thread_total) > len(_nodes(threads)):
        notes.mark_overflow()
    state.totals["reviewThreads"] = thread_total
    for thread in _nodes(threads):
        notes.thread(thread)
    return notes.finish(thread_total)


def review_blockers(pr: Json, head: str) -> set[str]:
    """Draft and review-decision blockers; these gate ready only."""
    blockers = {"draft"} if pr.get("isDraft") else set()
    decision = pr.get("reviewDecision")
    if decision == "CHANGES_REQUESTED":
        blockers.add(f"changes-requested:{_latest_change_request(pr) or head[:7]}")
    elif decision == "REVIEW_REQUIRED":
        blockers.add("review-required")
    return blockers


def _latest_change_request(pr: Json) -> str:
    """Id of the newest CHANGES_REQUESTED review, so a push does not re-arm it."""
    nodes = ((pr.get("reviews") or {}).get("nodes")) or []
    ids = [str(n.get("id", "")) for n in nodes if n.get("state") == "CHANGES_REQUESTED"]
    return ids[-1] if ids else ""
