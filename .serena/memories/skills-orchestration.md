# Orchestration Skills

**Extracted**: 2025-12-18
**Source**: `.agents/retrospective/2025-12-18-parallel-implementation-retrospective.md`

## Skill-Orchestration-001: Parallel Execution Time Savings

**Statement**: Spawning multiple implementer agents in parallel reduces wall-clock time by 40% compared to sequential execution

**Context**: When orchestrator has 3+ independent implementation tasks from the same analysis phase

**Evidence**: Sessions 19-21 completed in ~20 min parallel vs ~50 min sequential estimate (40% reduction)

**Atomicity**: 100%

- Single concept (parallel execution) ✓
- Specific metric (40% reduction) ✓
- Actionable (dispatch multiple agents) ✓
- Length: 14 words ✓

**Tag**: helpful

**Impact**: 10/10 - Significant wall-clock time savings

**Pattern**:

```markdown
# When analysis phase identifies 3+ independent implementation tasks:
1. Orchestrator dispatches multiple implementer agents in parallel
2. Each agent receives distinct analysis document (002, 003, 004)
3. Agents work independently until session end (HANDOFF update)
4. Orchestrator coordinates staging conflicts if any
```

**Validation**: 1 (Sessions 19-21)

**Created**: 2025-12-18

---

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

## Related Documents

- Source: `.agents/retrospective/2025-12-18-parallel-implementation-retrospective.md`
- Related: skills-planning (Skill-Planning-003 parallel exploration)
- Related: SESSION-PROTOCOL.md (session end requirements)
