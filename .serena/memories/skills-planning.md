# Planning & Requirements Skills

**Extracted**: 2025-12-16
**Source**: `.agents/retrospective/phase1-remediation-pr43.md`

## Skill-Planning-001: Task Descriptions with File Paths

**Statement**: Task descriptions with specific file paths and concrete examples reduce implementation time by eliminating ambiguity

**Context**: All planning artifacts - include file paths, line numbers, examples

**Evidence**: Phase 1 remediation completed in 4h vs. 5h estimated (20% faster) due to precise task breakdown with file paths

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 9/10

**Pattern**:

```markdown
## Task P0-1: Fix Path Violations
**Files**: 
- src/claude/explainer.md (line 45, 78)
- src/claude/architect.md (line 102)
**Example**: Change `path/to/file` → `[path/to/file](path/to/file)`
```

---

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

---

## Skill-Planning-004: Approval Checkpoint for Multi-File Changes (100%)

**Statement**: Multi-file changes (≥3 files or infrastructure) require user approval of architecture before implementation

**Context**: Before implementing complex changes that modify multiple files or affect infrastructure

**Trigger**: Implementation plan spans ≥3 files OR involves infrastructure (CI/CD, workflows, config)

**Evidence**: Session 03 (2025-12-18): User approved architecture for 14-file change (2,189 LOC). Result: zero implementation bugs, zero pivots. Plan executed exactly as designed.

**Atomicity**: 100%

- Specific trigger (≥3 files) ✓
- Single concept (approval gate) ✓
- Actionable (request approval) ✓
- Measurable (can verify approval received) ✓

**Impact**: Critical - Prevents wasted effort on incorrect architecture

**Category**: Planning Workflow

**Tag**: helpful

**Created**: 2025-12-18

**Validated**: 1 (AI Workflow Implementation session)

**Note**: This extends Skill-Planning-002 with specific trigger criteria.

---

## Related Documents

- Source: `.agents/retrospective/phase1-remediation-pr43.md`
- Source: `.agents/retrospective/2025-12-18-ai-workflow-implementation.md`
- Related: skills-workflow (Skill-Workflow-007 scope selection)
