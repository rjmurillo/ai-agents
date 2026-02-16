# Planning: Selfcontained Task Design

## Skill-Planning-002: Self-Contained Task Design

**Statement**: Design phase tasks to be independent and self-contained whenever possible to enable parallel execution and easy resumption

**Context**: Multi-task planning - minimize inter-task dependencies

**Evidence**: P0-1, P0-2, P0-3 could be completed in any order during Phase 1 remediation

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Application**:

1. Each task should be completable without waiting for other tasks
2. If dependencies exist, make them explicit with blocking notation
3. Include all context needed within the task description
4. Enable context window interruption recovery

---

## Related

- [planning-001-checkbox-manifest](planning-001-checkbox-manifest.md)
- [planning-001-task-descriptions-with-file-paths](planning-001-task-descriptions-with-file-paths.md)
- [planning-002-priority-consistency](planning-002-priority-consistency.md)
- [planning-003-parallel-exploration-pattern-95](planning-003-parallel-exploration-pattern-95.md)
- [planning-003-parallel-exploration-pattern](planning-003-parallel-exploration-pattern.md)
