# Planning: Parallel Exploration Pattern 95

## Skill-Planning-003: Parallel Exploration Pattern (95%)

**Statement**: For infrastructure work, launch parallel Explore agents to gather context concurrently before planning

**Context**: Infrastructure changes (workflows, CI/CD, multi-file). Launch before planning phase.

**Trigger**: Infrastructure or multi-file change request received

**Evidence**: Session 03 (2025-12-18): 3 parallel Explore agents (workflows, agent system, roadmap) reduced planning time by ~50%. Comprehensive understanding achieved before design started, resulting in zero discovered gaps during implementation.

**Atomicity**: 95%

- Specific action (launch parallel agents) ✓
- Single concept (parallel exploration) ✓
- Actionable (before planning) ✓
- Measurable (timestamps show concurrency) ✓
- Minor deduction: "infrastructure work" slightly vague (-5%)

**Impact**: 9/10 - Dramatically reduces planning time for complex changes

**Category**: Planning Workflow

**Tag**: helpful

**Created**: 2025-12-18

**Validated**: 1 (AI Workflow Implementation session)

**CRITICAL CAVEAT (Added 2025-12-18 from hyper-critical retrospective)**:
> Planning does NOT replace validation. Plan quality correlates with design clarity, 
> not implementation correctness. Session 03 had excellent planning but terrible 
> implementation due to untested assumptions. The code required 24+ fix commits.
> See: `.agents/retrospective/2025-12-18-hyper-critical-ai-workflow.md`

---

## Related

- [planning-001-checkbox-manifest](planning-001-checkbox-manifest.md)
- [planning-001-task-descriptions-with-file-paths](planning-001-task-descriptions-with-file-paths.md)
- [planning-002-priority-consistency](planning-002-priority-consistency.md)
- [planning-002-selfcontained-task-design](planning-002-selfcontained-task-design.md)
- [planning-003-parallel-exploration-pattern](planning-003-parallel-exploration-pattern.md)
