# Skill-Documentation-004: Pattern Consistency

## Statement

Use identical syntax for all instances when migrating patterns to maintain consistency

## Context

During migration execution across multiple files

## Evidence

Session 26 (2025-12-18): All tool call references use same format across 16 files during Serena memory reference migration

## Metrics

- Atomicity: 96%
- Impact: 8/10
- Category: documentation-maintenance, migration, consistency
- Created: 2025-12-18
- Tag: helpful
- Validated: 1

## Related Skills

- Skill-Documentation-001 (Systematic Migration Search)
- Skill-Documentation-002 (Reference Type Taxonomy)
- Skill-Documentation-003 (Fallback Preservation)

## Consistency Pattern

**Single canonical format** used across all files:

```markdown
Read [memory-name] memory using `mcp__serena__read_memory` with `memory_file_name="[memory-name]"`
  - If the Serena MCP is not available, then read `.serena/memories/[memory-name].md`
```

**Applied consistently**:

- SESSION-PROTOCOL.md: skill-usage-mandatory
- AGENTS.md: skills-design, skills-implementation
- ADRs: pattern-*, skill-*
- Agent docs: skills-*, memories-*

## Why Consistency Matters

1. **Cognitive Load**: One pattern to learn, not multiple variations
2. **Searchability**: Single grep pattern finds all instances
3. **Maintainability**: Future changes only need one template
4. **Quality**: Reduces copy-paste errors from mixing formats

## Pattern Variations to Avoid

**Inconsistent phrasing**:

- "Use mcp__serena__read_memory to read..."
- "Read using mcp__serena__read_memory..."
- "Access via mcp__serena__read_memory..."

**Inconsistent parameter syntax**:

- `memory_file_name="skill-name"`
- `memory_file_name='skill-name'`
- `memory_file_name=skill-name`

**Inconsistent fallback**:

- "If Serena MCP not available..."
- "If the Serena MCP is unavailable..."
- "When Serena unavailable..."

## Implementation Strategy

**Step 1: Define canonical pattern**

```markdown
# Create template with ALL variants accounted for
TEMPLATE: Read {name} memory using `mcp__serena__read_memory` with `memory_file_name="{name}"`
  - If the Serena MCP is not available, then read `.serena/memories/{name}.md`
```

**Step 2: Apply template systematically**

- Use find-replace with template
- Verify each instance matches template exactly
- Document any intentional deviations

**Step 3: Verify consistency**

```bash
# Search for pattern
grep -r "mcp__serena__read_memory" --include="*.md"

# Manually review for consistency
# All instances should be identical except for memory name
```

## Success Criteria

- Single canonical pattern documented before migration
- All instances use identical syntax (except parameters)
- No variation in phrasing, parameter quotes, or fallback wording
- Future maintainers can copy-paste pattern with confidence
