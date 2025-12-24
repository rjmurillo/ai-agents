# Skill-Planning-001: Task Descriptions with File Paths

**Statement**: Task descriptions with specific file paths and concrete examples reduce implementation time by eliminating ambiguity.

**Context**: All planning artifacts - include file paths, line numbers, examples.

**Evidence**: Phase 1 remediation completed in 4h vs. 5h estimated (20% faster).

**Atomicity**: 90% | **Impact**: 9/10

**Pattern**:

```markdown
## Task P0-1: Fix Path Violations
**Files**:
- src/claude/explainer.md (line 45, 78)
- src/claude/architect.md (line 102)
**Example**: Change `path/to/file` → `[path/to/file](path/to/file)`
```

## Skill-Planning-002: Self-Contained Task Design

**Statement**: Design phase tasks to be independent and self-contained whenever possible.

**Context**: Multi-task planning - minimize inter-task dependencies.

**Evidence**: P0-1, P0-2, P0-3 could be completed in any order during Phase 1.

**Atomicity**: 88% | **Impact**: 8/10

**Application**:
1. Each task completable without waiting for other tasks
2. If dependencies exist, make them explicit with blocking notation
3. Include all context needed within the task description
4. Enable context window interruption recovery
