# ADR-068/071/085 Metrics Update Debate Log

## Context

Issue #4917 adds a new PreToolUse hook (serena worktree scope guard).
This requires updating metrics in ADR-068, ADR-071, and ADR-085.

## Changes

- Shim count: 3 → 4
- Timeout budget: 110s → 120s
- Registration count: 4 → 5

## Verdict

**Self-review: ACCEPT**

Rationale: These are mechanical metrics updates that follow directly from
adding a new hook. No architectural decision is being changed. The host
timeout (125s) still provides 5s headroom over the 120s sum.

## References

- ADR-068: Consolidated hook dispatcher
- ADR-071: Plugin hook runtime-contract verification
- ADR-085: Cross-harness permission surface asymmetry
