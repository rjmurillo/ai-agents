# Skill-Documentation-001: Systematic Migration Search

## Statement

Search entire codebase for pattern before migration to identify all references

## Context

Before starting any documentation or code pattern migration

## Evidence

Session 26 (2025-12-18): Grep search identified 16 files with .serena/memories/ references; prevented missed references during Serena memory reference migration

## Metrics

- Atomicity: 95%
- Impact: 8/10
- Category: documentation-maintenance, migration, search
- Created: 2025-12-18
- Tag: helpful
- Validated: 1

## Related Skills

- Skill-Documentation-002 (Reference Type Taxonomy)
- Skill-Documentation-003 (Fallback Preservation)
- Skill-Documentation-004 (Pattern Consistency)

## Search Pattern

**Step 1: Define search pattern**
```bash
# Example: Search for file path pattern
grep -r ".serena/memories/" --include="*.md"

# Example: Search for tool call pattern
grep -r "mcp__cloudmcp-manager__" --include="*.md"
```

**Step 2: Analyze scope**
- Count files found
- Categorize by file type (docs, agents, configs)
- Identify edge cases

**Step 3: Create migration checklist**
- List all files to modify
- Note special cases (git commands, historical logs)
- Define replacement pattern

## Anti-Pattern

Starting migration without comprehensive search:
- Updating files one by one as you find them
- Relying on memory of where pattern exists
- Missing files because search was too narrow

## Success Criteria

- Single search command identifies all references
- Search pattern catches all variants (e.g., with/without quotes)
- Scope documented before making any changes
- Zero missed references after migration
