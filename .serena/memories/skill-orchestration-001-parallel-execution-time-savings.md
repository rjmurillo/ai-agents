# Skill-Orchestration-001: Parallel Execution Time Savings

## Statement

Parallel agent dispatch reduces wall-clock time by 30-50% for independent tasks despite coordination overhead

## Context

Use when multiple independent implementation tasks can proceed simultaneously

## Evidence

Sessions 19-21 (2025-12-18): Parallel implementation completed in ~20 minutes vs ~50 minutes (sequential estimate). 40% reduction.

## Metrics

- Atomicity: 100%
- Impact: 9/10
- Category: orchestration, efficiency, parallel-execution
- Created: 2025-12-18
- Tag: helpful
- Validated: 1

## Related Skills

- Skill-Orchestration-002 (Parallel HANDOFF Coordination)
- Skill-Analysis-001 (Comprehensive Analysis Standard)

## When to Use Parallel Execution

**Good candidates**:
- Multiple analysis tasks on independent topics
- Implementation of separate, non-conflicting features
- Research/exploration of different approaches
- Testing on different platforms

**Poor candidates**:
- Tasks with dependencies (A must complete before B)
- Tasks modifying same files (staging conflicts)
- Tasks requiring sequential context (learning from previous)
- Single complex task (no parallelism possible)

## Time Savings Calculation

```text
Sequential time = Task1 + Task2 + Task3
Parallel time = max(Task1, Task2, Task3) + coordination_overhead

Example (Sessions 19-21):
- Sequential: 17 min + 17 min + 17 min = 51 minutes
- Parallel: max(17, 17, 17) + 3 min coordination = 20 minutes
- Savings: (51 - 20) / 51 = 61% reduction
```

## Coordination Overhead

Expected overhead: 10-20% of parallel time
- Orchestrator dispatch
- Staging conflict resolution
- HANDOFF aggregation
- Commit coordination

## Success Criteria

- Wall-clock time < sum of individual task times
- All parallel tasks complete successfully
- Coordination overhead < 20% of parallel time
- No quality degradation vs sequential execution
