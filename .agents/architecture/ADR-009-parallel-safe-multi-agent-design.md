# ADR-009: Parallel-Safe Multi-Agent Design

## Status

Accepted

## Date

2025-12-20

## Context

The ai-agents system currently executes agents sequentially. When multiple agents work on related concerns, they must coordinate manually via HANDOFF.md and explicit delegation. This creates bottlenecks:

1. **Sequential execution**: Analyst → Architect → Implementer happens serially
2. **No conflict resolution**: When agents disagree, human intervention required
3. **Wasted potential**: Independent analyses could run in parallel
4. **Manual aggregation**: Results from multiple agents merged by orchestrator

Research into [ruvnet/claude-flow](https://github.com/ruvnet/claude-flow) demonstrated:

- 2.8-4.4x speed improvement through parallel execution
- 5 coordination modes: Centralized, Distributed, Hierarchical, Mesh, Hybrid
- Consensus algorithms: Majority, Weighted, Byzantine, Quorum, Unanimous
- Queen-worker swarm coordination model

## Decision

**Multi-agent coordination MUST include consensus mechanisms for conflict resolution.**

Specifically:

1. **Parallel dispatch**: Orchestrator can spawn multiple agents simultaneously for independent concerns
2. **Aggregation strategies**: Merge (non-conflicting), Vote (redundant), Escalate (conflicts)
3. **Consensus protocols**: Defined process for resolving agent disagreements
4. **Coordination modes**: Start with Hierarchical (orchestrator-led), evolve to Mesh

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Sequential only | Simple, predictable | Slow, bottlenecks | Current limitation |
| Parallel no consensus | Faster | Conflicts unresolved | Chaos risk |
| Parallel with consensus | Fast, safe | Complex to implement | **Chosen** |

### Trade-offs

- **Complexity**: Consensus mechanisms add coordination overhead
- **Determinism**: Parallel execution may produce different results on re-run
- **Debugging**: Harder to trace issues in concurrent workflows

## Consequences

### Positive

- 2-4x potential speedup for multi-agent tasks
- Conflicts resolved systematically, not ad-hoc
- Scales to larger agent swarms
- Enables voting patterns for quality assurance

### Negative

- Higher implementation complexity
- Potential for deadlocks if consensus fails
- Resource consumption increases with parallelism

### Neutral

- Orchestrator role evolves from dispatcher to coordinator

## Implementation Notes

### Aggregation Strategies

| Strategy | Use Case | Behavior |
|----------|----------|----------|
| **merge** | Non-conflicting outputs | Combine all outputs |
| **vote** | Redundant execution | Select majority |
| **escalate** | Conflicts detected | Route to high-level-advisor |

### Consensus Protocol (Hierarchical Mode)

```text
1. Orchestrator dispatches to N agents in parallel
2. Agents return results independently
3. Orchestrator checks for conflicts:
   - No conflicts → merge results
   - Soft conflicts → weighted vote (architect > implementer)
   - Hard conflicts → escalate to high-level-advisor
4. Final decision applied
```

### Phase 3 Implementation Order

1. Parallel Task invocation (Issue #168)
2. Basic merge aggregation
3. Voting mechanism (Issue #171)
4. Advanced coordination modes (Issue #175)

## Related Decisions

- ADR-007: Memory-First Architecture (parallel agents share memory)
- ADR-010: Quality Gates with Evaluator-Optimizer Pattern (parallel evaluation)

## References

- Epic #183: Claude-Flow Inspired Enhancements
- Issue #168: Parallel Agent Execution
- Issue #171: Consensus Mechanisms
- Issue #175: Swarm Coordination Modes
- Issue #177: Stream Processing
- [claude-flow swarm architecture](https://github.com/ruvnet/claude-flow)
- [Anthropic parallel execution patterns](https://www.anthropic.com/engineering/building-effective-agents)

---

*Template Version: 1.0*
*Origin: Epic #183 closing comment (2025-12-20)*
