# Skill-Documentation-003: Fallback Preservation

**Statement**: Include fallback clause when migrating to tool calls for graceful degradation.

**Context**: When abstracting direct file access to tool calls.

**Evidence**: Session 26: 5 fallback clauses added during Serena memory reference migration.

**Atomicity**: 96% | **Impact**: 9/10

**Pattern**:

```markdown
Read [memory-name] using `mcp__serena__read_memory` with `memory_file_name="[memory-name]"`
  - If Serena MCP not available, read `.serena/memories/[memory-name].md`
```

**Anti-Pattern**: Tool-only reference without fallback path.
