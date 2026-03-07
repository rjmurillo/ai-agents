# Planning: Task Descriptions With File Paths

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

## Related

- [planning-001-checkbox-manifest](planning-001-checkbox-manifest.md)
- [planning-002-priority-consistency](planning-002-priority-consistency.md)
- [planning-002-selfcontained-task-design](planning-002-selfcontained-task-design.md)
- [planning-003-parallel-exploration-pattern-95](planning-003-parallel-exploration-pattern-95.md)
- [planning-003-parallel-exploration-pattern](planning-003-parallel-exploration-pattern.md)
