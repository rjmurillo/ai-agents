# Planning: Approval Checkpoint For Multifile Changes

## Skill-Planning-004: Approval Checkpoint for Multi-File Changes

**Statement**: Multi-file changes (≥3 files or infrastructure) require user approval of architecture before implementation.

**Context**: Before implementing complex changes.

**Trigger**: ≥3 files OR infrastructure (CI/CD, workflows, config)

**Evidence**: Session 03: User approved architecture for 14-file change (2,189 LOC).

**Atomicity**: 100% | **Impact**: Critical

**Note**: Approval prevents wasted effort on wrong architecture, but does NOT guarantee bug-free implementation.

## Related

- [planning-001-checkbox-manifest](planning-001-checkbox-manifest.md)
- [planning-001-task-descriptions-with-file-paths](planning-001-task-descriptions-with-file-paths.md)
- [planning-002-priority-consistency](planning-002-priority-consistency.md)
- [planning-002-selfcontained-task-design](planning-002-selfcontained-task-design.md)
- [planning-003-parallel-exploration-pattern-95](planning-003-parallel-exploration-pattern-95.md)
