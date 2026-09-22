<!-- placement: evidence; reason: a dated routing observation, kept as rationale for the routing owners rather than as a routing table -->

# Orchestration: What Skipping Triage Cost in Session 04

Authoritative owners: `.claude/skills/autoplan/SKILL.md` routes a request that
names no skill, and `.claude/agents/orchestrator.md` Routing Algorithm
sequences the agents. `CLAUDE.md` states the default for non-trivial tasks.

## Observation (2025-12-24, Session 04)

The request was "fix aggregation failures in #357". Dispatched straight to an
implementer, the work produced a fix for a cause nobody had established, and
the work was discarded. Routed through triage instead, the sequence resolved to
analyst, then architect, then implementer, and the second attempt held.

## Transferable reading

The cost of skipping triage is not a slower path; it is a confident wrong fix
that looks finished. The signal that triage is needed is an unknown root cause,
not the size of the change: a one-file fix for an undiagnosed failure carries
the same risk as a ten-file one.

## Related

- [orchestration-parallel-execution](orchestration-parallel-execution.md)
- [orchestration-pr-chain](orchestration-pr-chain.md)
- [analysis/analysis-002-rca-before-implementation](../analysis/analysis-002-rca-before-implementation.md)
