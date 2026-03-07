# Orchestration: Parallel Handoff Coordination

## Skill-Orchestration-002: Parallel HANDOFF Coordination

**Statement**: When running parallel sessions, orchestrator MUST consolidate HANDOFF.md updates to prevent staging conflicts

**Context**: Multiple agents updating HANDOFF.md simultaneously causes git staging conflicts

**Evidence**: Session 19 commit bundled with Session 20 due to HANDOFF staging conflict

**Atomicity**: 100%

- Single concept (HANDOFF coordination) ✓
- Specific problem (staging conflicts) ✓
- Actionable (orchestrator consolidation) ✓
- Length: 12 words ✓

**Tag**: CRITICAL

**Impact**: 9/10 - Prevents commit bundling and maintains atomic commits

**Implementation**:

Orchestrator should:

1. Collect session summaries from all parallel agents
2. Aggregate summaries into single HANDOFF.md update
3. Commit all changes in coordinated sequence (not bundled)

**Anti-Pattern**: Allowing parallel agents to update HANDOFF.md independently

**Validation**: 1 (Sessions 19 & 20 staging conflict)

**Created**: 2025-12-18

---

## Related

- [orchestration-001-parallel-execution-time-savings](orchestration-001-parallel-execution-time-savings.md)
- [orchestration-003-handoff-validation-gate](orchestration-003-handoff-validation-gate.md)
- [orchestration-003-orchestrator-first-routing](orchestration-003-orchestrator-first-routing.md)
- [orchestration-copilot-swe-anti-patterns](orchestration-copilot-swe-anti-patterns.md)
- [orchestration-handoff-coordination](orchestration-handoff-coordination.md)
