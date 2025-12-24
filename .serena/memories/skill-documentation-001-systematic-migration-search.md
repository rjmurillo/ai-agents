# Skill-Documentation-001: Systematic Migration Search

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
