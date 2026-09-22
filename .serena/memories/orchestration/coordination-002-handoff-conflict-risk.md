<!-- placement: evidence; reason: a per-branch conflict count that ADR-014 summarizes only as a repository-wide rate -->

# Coordination: What HANDOFF.md Conflicts Cost One Branch

`.agents/HANDOFF.md` no longer exists.
`.agents/architecture/ADR-014-distributed-handoff-architecture.md` decided its
retirement and records the repository-wide rate. This file keeps the
branch-level numbers ADR-014 does not carry.

## Observation (2025-12-22, PR #206)

Branch `fix/session-41-cleanup` hit 4 conflicts in `.agents/HANDOFF.md` over 3
days. Session 58 on that branch needed manual merge resolution. Main advanced
through Sessions 55 to 61 while the branch carried Sessions 55 to 58, so the
shared "Session History" table diverged on both sides at once.

## Why that file and not others

Every session wrote to one table in one file, and several agents plus humans
worked concurrently. A long-lived branch therefore accumulated a conflict per
session on main, independent of what the branch itself changed. The conflict
rate tracked calendar time on the branch, not its diff.

## Related

- [coordination-001-branch-isolation-gate](coordination-001-branch-isolation-gate.md)
- [../protocol/protocol-014-trust-antipattern](../protocol/protocol-014-trust-antipattern.md)
