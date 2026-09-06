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

    The single definition of what counts as a subagent event. It was written
    twice, once for the support probe and once for the concurrency walk, so a
    runtime spelling its events `sub_agent` or `child.start` would have been
    taught to one probe and not the other, and the two would have disagreed
    about the same stream without either failing.
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
    asked for. A start counts toward the peak only while enough completion
    boundaries remain in the stream to close it and every child already open
    beside it. Without that, a run of N starts is indistinguishable from N
    sequential children whose completions were never emitted, and assuming
    they overlapped would report the requested number wearing the observed
    number's label.

    One global "a completion appeared somewhere" flag was not enough: it let a
    single early pair license an unbounded tail of unclosed starts, so
    `start, end, start, start, start` reported three. The same tail now
    reports one, and a truncated `start, start, end` reports one rather than
    two. Both directions are the fail-closed one.

    Returns `None` when no start is backed by a completion, and when a
    completion arrives with no child open, which is a stream whose boundaries
    do not describe a coherent run. Claude's `tool_use` blocks for `Agent` and
    `Task` carry no boundary of either kind, so they resolve to `None` here.
    """
    boundaries: list[bool] = []
    for event in events:
        lowered = _subagent_event_kind(event)
        if lowered is None:
            continue
        if any(hint in lowered for hint in _END_HINTS):
            boundaries.append(False)
        elif any(hint in lowered for hint in _START_HINTS):
            boundaries.append(True)
    completions_left = boundaries.count(False)
    depth = 0
    peak = 0
    for is_start in boundaries:
        if not is_start:
            if depth == 0:
                return None
            depth -= 1
            completions_left -= 1
            continue
        depth += 1
        if depth <= completions_left:
            peak = max(peak, depth)
    if peak == 0:
        return None
    return peak
