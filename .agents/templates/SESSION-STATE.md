# Session State

Track in-progress work so a session crash or compaction does not lose progress.
The next session (or the next agent after a handoff) inherits this file.

## Where the live instance lives

This file is the template. The live, per-issue instance is written to:

```text
.agents/sessions/state/{issue-number}.md
```

One file per issue under active work. An agent working issue #1234 reads and
writes `.agents/sessions/state/1234.md`. When work on the issue completes, the
state file is removed (the session log and PR carry the durable record).

## When agents write to it

Refresh the live instance after each major step, not at the end:

1. After completing a step, update **Current Step** and **Files Modified**.
2. Before starting a multi-file change, record the plan in **Estimated
   Remaining Work** so a crash mid-change leaves a recoverable trail.
3. When a **Context Pressure** signal fires, set the level and checkpoint.
4. On every irreversible or non-obvious decision, append to **Decisions Made**.

Updating after each step (not just at session end) is the point: a session that
dies at step 4 of 7 must leave a file that reflects 4 done, 3 remaining.

## Current Step

Step _N_ of _total_: [description of current step]

## Files Modified

| File | Change |
|------|--------|
| _path_ | _brief description_ |

## Tests Status

- [ ] Tests written
- [ ] Tests passing

## Estimated Remaining Work

| Step | Complexity | Status |
|------|-----------|--------|
| _next step_ | S/M/L | pending |

## Context Pressure

**Level**: LOW | MEDIUM | HIGH | CRITICAL

Signals observed:
- [ ] Re-reading files already read this session
- [ ] Cannot recall acceptance criteria without scrolling
- [ ] Writing stubs or TODO placeholders where real code belongs
- [ ] Re-delegating tasks an agent already completed
- [ ] Synthesis omits or contradicts earlier findings

## Decisions Made

| Decision | Rationale | Reversible? |
|----------|-----------|-------------|
| _what_ | _why_ | yes/no |

## Handoff Notes

_What the next session needs to know to continue without re-reading everything._
