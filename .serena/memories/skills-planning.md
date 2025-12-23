# Planning & Requirements Skills

**Created**: 2025-12-16
**Updated**: 2025-12-23 (consolidated from 3 atomic memories)
**Sources**: Various retrospectives
**Skills**: 7

---

## Skill-Planning-001: Task Descriptions with File Paths

**Statement**: Task descriptions with specific file paths and concrete examples reduce implementation time by eliminating ambiguity

**Context**: All planning artifacts - include file paths, line numbers, examples

**Evidence**: Phase 1 remediation completed in 4h vs. 5h estimated (20% faster)

**Atomicity**: 90% | **Impact**: 9/10 | **Tag**: helpful

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

**Statement**: Design phase tasks to be independent and self-contained whenever possible

**Context**: Multi-task planning - minimize inter-task dependencies

**Evidence**: P0-1, P0-2, P0-3 could be completed in any order during Phase 1 remediation

**Atomicity**: 88% | **Impact**: 8/10 | **Tag**: helpful

**Application**:
1. Each task completable without waiting for other tasks
2. If dependencies exist, make them explicit with blocking notation
3. Include all context needed within the task description
4. Enable context window interruption recovery

---

## Skill-Planning-003: Parallel Exploration Pattern

**Statement**: For infrastructure work, launch parallel Explore agents to gather context concurrently before planning

**Context**: Infrastructure changes (workflows, CI/CD, multi-file). Launch before planning.

**Evidence**: Session 03: 3 parallel Explore agents reduced planning time by ~50%

**Atomicity**: 95% | **Impact**: 9/10 | **Tag**: helpful

**CRITICAL CAVEAT**: Planning does NOT replace validation. Session 03 had excellent planning but required 24+ fix commits due to untested assumptions.

---

## Skill-Planning-004: Approval Checkpoint for Multi-File Changes

**Statement**: Multi-file changes (≥3 files or infrastructure) require user approval of architecture before implementation

**Context**: Before implementing complex changes

**Trigger**: ≥3 files OR infrastructure (CI/CD, workflows, config)

**Evidence**: Session 03: User approved architecture for 14-file change (2,189 LOC)

**Atomicity**: 100% | **Impact**: Critical | **Tag**: helpful

**Note**: Approval prevents wasted effort on wrong architecture, but does NOT guarantee bug-free implementation.

---

## Skill-Planning-005: Checkbox Manifest for Analysis

**Statement**: Analysis documents with N recommendations require checkbox manifest at top linking each item to its section

**Context**: When creating analysis documents that will drive implementation

**Evidence**: Personality integration: 4 of 20 items missed without tracking manifest (20% miss rate)

**Atomicity**: 92% | **Impact**: 9/10 | **Tag**: helpful

**Pattern**:

```markdown
## Implementation Checklist

- [ ] ITEM-001: Description of first recommendation (see Section X.Y)
- [ ] ITEM-002: Description of second recommendation (see Section X.Y)

Total Items: N | Implemented: M | Gap: N-M
```

**When to Apply**: Analysis documents with 3+ recommendations

---

## Skill-Planning-006: Priority Consistency for Shared Recommendations

**Statement**: Recommendations affecting multiple agents must list identical priority across all affected agent rows

**Context**: When creating multi-agent recommendation tables

**Evidence**: FORMAT-001 split across High (explainer) and Low (roadmap) led to roadmap instance being skipped

**Atomicity**: 95% | **Impact**: 8/10 | **Tag**: helpful

**Correct**:

```markdown
| Agent     | Recommendation             | Priority |
|-----------|----------------------------|----------|
| explainer | Add anti-marketing section | Medium   |
| roadmap   | Add anti-marketing section | Medium   |
```

**Validation Rule**: If recommendation affects agents [A, B], priority must be identical for A and B rows.

---

## Skill-Planning-007: Multi-Platform Agent Scope

**Statement**: Agent changes affect multiple platforms: Claude, templates, copilot-cli, vs-code-agents (72 files minimum)

**Context**: During planning phase for agent enhancements

**Evidence**: Commit 3e74c7e: Modified 18 files. Full scope should have been 72 files (4 platforms).

**Atomicity**: 88% | **Impact**: 8/10 | **Tag**: helpful

**Platform Scope Checklist**:

| Platform | Directory | Count |
|----------|-----------|-------|
| Claude Code | src/claude/ | 18 agents |
| Templates | templates/agents/ | 18 agents |
| Copilot CLI | src/copilot-cli/ | 18 agents |
| VS Code | src/vs-code-agents/ | 18 agents |
| **Total** | **4 platforms** | **72 files minimum** |

**Common Gaps**: Modifying Claude only (18), missing templates (36), forgetting copilot-cli/vs-code-agents

---

## Quick Reference

| Skill | When to Use |
|-------|-------------|
| 001 | Writing task descriptions - include file paths |
| 002 | Designing tasks - make self-contained |
| 003 | Infrastructure changes - parallel explore first |
| 004 | ≥3 files - get approval before implementing |
| 005 | Analysis documents - add checkbox manifest |
| 006 | Multi-agent tables - consistent priorities |
| 007 | Agent changes - scope all 4 platforms |

## Related

- skills-workflow (Skill-Workflow-007 scope selection)
- Skill-Deployment-001 (Agent Self-Containment)
- Skill-Architecture-015 (Deployment Path Validation)
