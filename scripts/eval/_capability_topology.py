"""Subagent topology observed in a runtime's own event stream.

Split out of `_capability_probes` after PR #5623's review. The seam is what
changes together rather than what things are: the support probe and the
concurrency walk both read the same event vocabulary, so a harness spelling
its child events differently is one edit here instead of two edits in a module
that also builds plans and runs subprocesses. Override probing does not share
this vocabulary; it reads values through `_capability_evidence` instead.

The duplication that pointed at this seam was real. `_subagent_event_kind` was
written twice, once for each reader, so a new spelling taught to one and not
the other would have made the two probes disagree about the same stream with
neither failing.

Observation only. Nothing here runs a CLI, and nothing here decides a
`CapabilityStatus`; `_capability_probes` owns both.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from _runtime_output import traces

#: The event type Copilot attaches a backend answer to. `copilot_result`
_START_HINTS: tuple[str, ...] = ("start", "begin", "launch", "spawn")
_END_HINTS: tuple[str, ...] = ("complete", "end", "stop", "finish", "exit", "result")


def _subagent_event_kind(event: Mapping[str, object]) -> str | None:
    """Return the lowercased type when the runtime emitted this about a child.

    The single definition of what counts as a subagent event. Only the
    contiguous text `subagent` is recognised; a runtime spelling its events
    `sub_agent` or `child.start` produces no lifecycle evidence at all, and
    every probe here then reports UNVERIFIED rather than guessing. Teaching a
    new spelling is an edit to this function, which is the point of it being
    one function: the same predicate was written twice before, once per
    reader, so a spelling taught to one and not the other would have made the
    two probes disagree about the same stream with neither failing.
    """
    kind = event.get("type")
    if isinstance(kind, str) and "subagent" in kind.lower():
        return kind.lower()
    return None


def subagent_lifecycle_events(
    events: Sequence[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    """Return the runtime's own subagent lifecycle events.

    Split out from `_runtime_output.traces`, which merges these with Claude
    `tool_use` blocks named `Agent` or `Task`. That merge is right for a
    parity report, which wants everything the run touched, and wrong here: a
    `tool_use` block is the model asking for a child, emitted before anything
    runs and present even when the launch fails. Counting one as a launch is
    the config-echo failure wearing a different observable, so only events the
    runtime itself emitted about a child's lifecycle are counted.
    """
    return [event for event in events if _subagent_event_kind(event) is not None]


def requested_subagent_tools(events: Sequence[Mapping[str, object]]) -> int:
    """Count subagent tool requests, which are asks rather than launches."""
    _, subagents = traces(events)
    return len(subagents) - len(subagent_lifecycle_events(events))


def max_concurrent_children(events: Sequence[Mapping[str, object]]) -> int | None:
    """Return the peak number of children in flight at once, or `None`.

    Derived by walking subagent start and completion boundaries in order, so
    the result is what the runtime reported running, never what the probe
    asked for.

    Returns `None` unless every start the stream opens is also closed by it. A
    stream that ends with children still running has not shown its maximum:
    the walk can only report the peak among the children it watched finish,
    and publishing that as a verified maximum would claim a limit lower than a
    number of children the same stream shows starting. An earlier revision did
    exactly that, reporting one for `start, end, start, start, start`, and
    called it conservative. It is not: for a maximum, too low is a false claim
    rather than a cautious one, so an incomplete stream now measures nothing.

    Also returns `None` for a completion arriving with no child open, which is
    a stream whose boundaries do not describe a coherent run, and when no
    start appears at all. Claude's `tool_use` blocks for `Agent` and `Task`
    carry no boundary of either kind, so they resolve to `None` here.
    """
    depth = 0
    peak = 0
    for event in events:
        lowered = _subagent_event_kind(event)
        if lowered is None:
            continue
        if any(hint in lowered for hint in _END_HINTS):
            if depth == 0:
                return None
            depth -= 1
        elif any(hint in lowered for hint in _START_HINTS):
            depth += 1
            peak = max(peak, depth)
    if depth != 0 or peak == 0:
        return None
    return peak
