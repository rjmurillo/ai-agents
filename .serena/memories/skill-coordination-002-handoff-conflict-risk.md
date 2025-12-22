# Skill-Coordination-002: HANDOFF.md High-Conflict Risk

## Statement

HANDOFF.md is a high-incursion risk file requiring defensive merge strategies when working on long-lived branches.

## Context

Multi-agent coordination with parallel sessions across branches

## Problem

HANDOFF.md is modified in nearly every agent session, creating high conflict probability:

1. **Frequent Updates**: Every session must update HANDOFF.md (Session Protocol MUST requirement)
2. **Parallel Work**: Multiple bots (rjmurillo-bot) and humans work concurrently
3. **Session History Collisions**: The "Session History (Last 10)" table is the most conflict-prone section
4. **Branch Divergence**: Long-lived feature branches accumulate session debt vs main

## Evidence

- PR #206: fix/session-41-cleanup branch had 4 HANDOFF.md conflicts over 3 days
- Session 58-PR206 (2025-12-22): Required manual merge resolution
- Main branch advanced through Sessions 55-61 while PR #206 branch had Sessions 55-58

## Pattern

### Defensive Strategies

| Strategy | When | Benefit |
|----------|------|---------|
| Frequent rebases | Daily on long-lived branches | Smaller conflicts |
| Session ID suffixes | Parallel work on same day | Avoid collision (e.g., Session-58-PR206) |
| Merge before commit | Before final session commit | Fresh base |
| Conflict-aware sections | Session History table | Easier resolution |

### Resolution Protocol

When HANDOFF.md conflict occurs:

1. Keep ALL session entries from both sides (no data loss)
2. Sort by date (newest first)
3. Add suffix to disambiguate same-numbered sessions (e.g., Session-58-PR206 vs Session-58)
4. Verify 10 most recent sessions shown

### Anti-Pattern

- Discarding session history entries during merge (loses audit trail)
- Ignoring HANDOFF.md conflicts until PR merge (compounds complexity)
- Working on long-lived branches without periodic rebases

## Atomicity

92%

## Impact

8/10 (affects every multi-session workflow)

## Created

2025-12-22

## Validated

1 (PR #206 Session 58-PR206)

## Tags

coordination, git, merge-conflicts, parallel-work

## Related Skills

- Skill-Coordination-001: Branch Isolation Gate
- Skill-Protocol-005: Template Enforcement
- Skill-Tracking-002: Incremental Checklist
