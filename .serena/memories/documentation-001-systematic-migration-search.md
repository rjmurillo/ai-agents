# Documentation: Systematic Migration Search

## Skill-Documentation-001: Systematic Migration Search

**Statement**: Search entire codebase for pattern before migration to identify all references.

**Context**: Before starting any documentation or code pattern migration.

**Evidence**: Session 26: Grep search identified 16 files with .serena/memories/ references.

**Atomicity**: 95% | **Impact**: 8/10

**Search Pattern**:

```bash
# Step 1: Define search pattern
grep -r ".serena/memories/" --include="*.md"
grep -r "mcp__cloudmcp-manager__" --include="*.md"

# Step 2: Analyze scope - count files, categorize by type, identify edge cases
# Step 3: Create migration checklist before making changes
```

**Anti-Pattern**: Starting migration without comprehensive search.

## Related

- [documentation-001-templatefirst-documentation-workflow](documentation-001-templatefirst-documentation-workflow.md)
- [documentation-002-reference-type-taxonomy](documentation-002-reference-type-taxonomy.md)
- [documentation-003-fallback-preservation](documentation-003-fallback-preservation.md)
- [documentation-004-pattern-consistency](documentation-004-pattern-consistency.md)
- [documentation-006-self-contained-operational-prompts](documentation-006-self-contained-operational-prompts.md)
