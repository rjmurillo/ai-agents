# Planning: Exploration & Approval Patterns

## Skill-Planning-003: Parallel Exploration Pattern

**Statement**: For infrastructure work, launch parallel Explore agents to gather context concurrently before planning.

**Context**: Infrastructure changes (workflows, CI/CD, multi-file). Launch before planning.

**Evidence**: Session 03: 3 parallel Explore agents reduced planning time by ~50%.

**Atomicity**: 95% | **Impact**: 9/10

**CRITICAL CAVEAT**: Planning does NOT replace validation. Session 03 had excellent planning but required 24+ fix commits due to untested assumptions.

## Skill-Planning-004: Approval Checkpoint for Multi-File Changes

**Statement**: Multi-file changes (≥3 files or infrastructure) require user approval of architecture before implementation.

**Context**: Before implementing complex changes.

**Trigger**: ≥3 files OR infrastructure (CI/CD, workflows, config)

**Evidence**: Session 03: User approved architecture for 14-file change (2,189 LOC).

**Atomicity**: 100% | **Impact**: Critical

**Note**: Approval prevents wasted effort on wrong architecture, but does NOT guarantee bug-free implementation.

## Related

- [planning-003-parallel-exploration-pattern](planning-003-parallel-exploration-pattern.md)
- [planning-004-approval-checkpoint](planning-004-approval-checkpoint.md)
- [planning-checkbox-manifest](planning-checkbox-manifest.md)
- [planning-multi-platform](planning-multi-platform.md)
- [planning-priority-consistency](planning-priority-consistency.md)
