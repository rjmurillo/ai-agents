# Planning: Parallel Exploration Pattern

## Skill-Planning-003: Parallel Exploration Pattern

**Statement**: For infrastructure work, launch parallel Explore agents to gather context concurrently before planning.

**Context**: Infrastructure changes (workflows, CI/CD, multi-file). Launch before planning.

**Evidence**: Session 03: 3 parallel Explore agents reduced planning time by ~50%.

**Atomicity**: 95% | **Impact**: 9/10

**CRITICAL CAVEAT**: Planning does NOT replace validation. Session 03 had excellent planning but required 24+ fix commits due to untested assumptions.

## Related

- [planning-001-checkbox-manifest](planning-001-checkbox-manifest.md)
- [planning-001-task-descriptions-with-file-paths](planning-001-task-descriptions-with-file-paths.md)
- [planning-002-priority-consistency](planning-002-priority-consistency.md)
- [planning-002-selfcontained-task-design](planning-002-selfcontained-task-design.md)
- [planning-003-parallel-exploration-pattern-95](planning-003-parallel-exploration-pattern-95.md)
