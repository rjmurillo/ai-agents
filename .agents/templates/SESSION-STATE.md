# Session State

Track in-progress work so a session crash or compaction does not lose progress.
Agents update this file after each major step. The next session inherits it.

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
