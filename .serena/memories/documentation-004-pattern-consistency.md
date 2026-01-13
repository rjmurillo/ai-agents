# Skill-Documentation-004: Pattern Consistency

**Statement**: Use identical syntax for all instances when migrating patterns.

**Evidence**: Session 26: All tool call references use same format across 16 files.

**Atomicity**: 96% | **Impact**: 8/10

**Canonical Pattern**:

```markdown
Read {name} memory using `mcp__serena__read_memory` with `memory_file_name="{name}"`
  - If the Serena MCP is not available, then read `.serena/memories/{name}.md`
```

**Why**: One pattern to learn, single grep finds all instances, future changes need one template.

## Related

- [documentation-001-systematic-migration-search](documentation-001-systematic-migration-search.md)
- [documentation-002-reference-type-taxonomy](documentation-002-reference-type-taxonomy.md)
- [documentation-003-fallback-preservation](documentation-003-fallback-preservation.md)
- [documentation-006-self-contained-operational-prompts](documentation-006-self-contained-operational-prompts.md)
- [documentation-007-self-contained-artifacts](documentation-007-self-contained-artifacts.md)
