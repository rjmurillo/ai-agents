<!-- placement: evidence; reason: a measured wall-clock comparison between parallel and sequential agent dispatch -->

# Orchestration: Measured Savings From Parallel Agent Dispatch

Authoritative owner: `.claude/agents/orchestrator.md` Routing Algorithm decides
when to dispatch in parallel. This file holds the measurement behind it.

## Measurement (2025-12-18, Sessions 19-21)

Three independent implementation tasks:

- Sequential estimate: about 50 minutes.
- Parallel actual: about 20 minutes, including coordination.
- Reduction: about 40%.

Coordination overhead ran 10 to 20% of the parallel wall clock: dispatch,
conflict resolution, and result aggregation.

## Where the saving does not appear

Observed cases where parallel dispatch cost more than it saved:

- Tasks with a dependency, where B cannot start until A finishes.
- Tasks that modify the same files, which trade wall clock for conflict
  resolution.
- Tasks that need the prior task's context to be framed correctly.

## Related

- [orchestration-003-orchestrator-first-routing](orchestration-003-orchestrator-first-routing.md)
- [coordination-001-branch-isolation-gate](coordination-001-branch-isolation-gate.md)
- [orchestration-pr-chain](orchestration-pr-chain.md)
