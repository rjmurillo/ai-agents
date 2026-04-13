# Forgetful Import Pattern

**Created**: 2026-01-18
**Purpose**: Documented pattern for importing Serena observation files into Forgetful MCP for semantic search.

## Overview

This document captures the repeatable pattern validated during the Phase 1 pilot import of `testing-observations.md` into Forgetful.

## Phase 1 Pilot Results

| Metric | Result |
|--------|--------|
| Source file | `.serena/memories/testing-observations.md` |
| Total learnings | 33 (16 HIGH + 17 MED) |
| Forgetful project ID | 2 |
| Memory IDs created | 221-253 |
| Semantic search validation | PASSED |

## Import Pattern

### Step 1: Create Project

```python
execute_forgetful_tool("create_project", {
    "name": "ai-agents-{domain}",  # e.g., "ai-agents-testing"
    "description": "Domain description with scope and sources",
    "project_type": "development",
    "repo_name": "rjmurillo/ai-agents",
    "notes": "Source: .serena/memories/{domain}-observations.md"
})
```

**Returns**: Project ID for linking memories

### Step 2: Extract Learnings by Confidence

Parse the observation file sections:

| Section | Confidence Level | Forgetful Importance |
|---------|------------------|---------------------|
| Constraints (HIGH) | HIGH | 9-10 |
| Preferences (MED) | MED | 7-8 |
| Edge Cases (MED) | MED | 7 |
| Notes for Review (LOW) | LOW | 5-6 |

### Step 3: Create Memories with Provenance

For each learning:

```python
execute_forgetful_tool("create_memory", {
    "title": "Short descriptive title",  # e.g., "Integration tests must test end-to-end behavior"
    "content": "Full learning text with evidence",
    "context": "Observation from Session {session}, {date}. {domain} {type}.",
    "keywords": ["domain-specific", "tags", "for", "search"],
    "tags": [
        "testing",           # Domain
        "constraint",        # OR "preference", "edge-case"
        "high-confidence",   # OR "medium-confidence", "low-confidence"
        "pester"            # Specific technology
    ],
    "importance": 10,        # 9-10 for HIGH, 7-8 for MED, 5-6 for LOW
    "project_ids": [project_id],

    # Provenance fields (required)
    "source_repo": "rjmurillo/ai-agents",
    "source_files": [".serena/memories/{domain}-observations.md"],
    "confidence": 1.0,       # 1.0 for HIGH, 0.85 for MED, 0.7 for LOW
    "encoding_agent": "claude-opus-4-5"  # OR sonnet, etc.
})
```

**Auto-linking**: Forgetful automatically links new memories to semantically similar existing memories (visible in `linked_memory_ids` response).

### Step 4: Validate Semantic Search

Test queries that should return relevant results:

```python
execute_forgetful_tool("query_memory", {
    "query": "domain-specific search terms",
    "query_context": "Why searching for this",
    "project_ids": [project_id]  # Filter to specific project
})
```

**Validation queries used for testing domain**:
- "pester test failures" - returned ANSI codes, Pester syntax, rollout validation
- "CI testing patterns pipeline automation" - returned Read-Host, CI mode, matrix builds
- "cross-platform Windows Linux testing" - returned cross-platform, mock CLI, chmod

## Tag Taxonomy

### Confidence Tags
- `high-confidence` - Corrections that MUST be followed
- `medium-confidence` - Preferences that SHOULD be followed
- `low-confidence` - Observations awaiting validation

### Type Tags
- `constraint` - Hard requirements
- `preference` - Best practices
- `edge-case` - Scenarios to handle
- `anti-pattern` - What to avoid

### Domain Tags (examples)
- `testing`, `pester`, `ci-cd`, `powershell`, `github-actions`
- `pr-review`, `github`, `memory`, `architecture`

## Batch Import Optimization

For large observation files, batch memory creation in groups of 4-5 per tool call:

```python
# Call 4 create_memory operations in parallel
# Forgetful handles auto-linking between batches
# Total import time: ~5 minutes for 33 memories
```

## Next Steps (Remaining Phases)

### Phase 2: High-Value Domains
- `pr-review-observations.md` (17 learnings)
- `github-observations.md` (10 learnings)
- `powershell-observations.md` (18 learnings)

### Phase 3: Remaining Files
- 31 additional observation files
- Bulk import script based on this pattern

## Related

- `.serena/memories/forgetful-migration-plan.md` - Migration strategy
- `.claude/skills/forgetful/` - Forgetful skill integration
- `AGENTS.md` - Memory system documentation
