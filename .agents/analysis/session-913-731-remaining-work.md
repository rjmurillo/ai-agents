# Issue #731: Remaining Work Analysis

**Session**: 913
**Date**: 2026-01-24
**Status**: #751 Complete, #731 In Progress

## Completed (#751)

- ✅ Added Memory Interface Decision Matrix to AGENTS.md
- ✅ Verified cross-references in memory SKILL.md and context-retrieval.md
- ✅ Committed changes (commit f8033af5)

## Remaining Work (#731)

### Scope

Update agent prompts to use Memory Router interface instead of deprecated cloudmcp-manager.

**Total References**:
- 81 cloudmcp references across 17 agent files
- Top files: analyst.md (11), retrospective.md (10), orchestrator.md (8)

### Replacement Strategy

| Old Pattern | New Pattern | Rationale |
|-------------|-------------|-----------|
| `mcp__cloudmcp-manager__memory-search_nodes` | `execute_forgetful_tool("query_memory")` | Forgetful is the semantic search backend per ADR-037 |
| `mcp__cloudmcp-manager__memory-add_observations` | `execute_forgetful_tool("create_memory")` | Forgetful is now the memory creation interface |
| `mcp__cloudmcp-manager__memory-create_entities` | `execute_forgetful_tool("create_entity")` | Forgetful handles entities |
| `mcp__cloudmcp-manager__memory-create_relations` | `execute_forgetful_tool("link_memories")` | Forgetful handles relations |

### Infrastructure Calls (KEEP AS-IS)

DO NOT change these - they're infrastructure, not memory search:
- `mcp__serena__activate_project`
- `mcp__serena__initial_instructions`

### CRUD Operations (KEEP AS-IS)

DO NOT change these - they're file operations, not search:
- `mcp__serena__read_memory` (reading specific memory by name)
- `mcp__serena__write_memory` (creating new memory file)
- `mcp__serena__edit_memory` (updating memory)
- `mcp__serena__delete_memory` (removing memory)
- `mcp__serena__list_memories` (listing all memories)

## Files to Update

### Priority 1 (Most References)

1. `.claude/agents/analyst.md` (11 references)
2. `.claude/agents/retrospective.md` (10 references)
3. `.claude/agents/orchestrator.md` (8 references)

### Priority 2 (Medium References)

4-7. `.claude/agents/{task-generator,security,roadmap,qa}.md` (4 each)

### Priority 3 (Standard References)

8-16. `.claude/agents/{pr-comment-responder,planner,independent-thinker,implementer,explainer,devops,critic,architect,high-level-advisor}.md` (4-1 each)

17. `.claude/agents/AGENTS.md` (3 references)

## Acceptance Criteria (from #731)

```bash
# Must return 0 matches for deprecated cloudmcp calls
grep -c "cloudmcp" .claude/agents/*.md
# Expected: 0

# Must return matches for Memory Router usage
grep -c "Search-Memory\|execute_forgetful_tool" .claude/agents/*.md
# Expected: >0
```

## Implementation Notes

### Example Transformation (retrospective.md line 842)

**Before**:
```markdown
mcp__cloudmcp-manager__memory-search_nodes
```

**After**:
```markdown
execute_forgetful_tool("query_memory", {
    "query": "[search terms]",
    "query_context": "[context for ranking]"
})
```

### Example Transformation (retrospective.md line 1175)

**Before**:
```markdown
mcp__cloudmcp-manager__memory-create_entities
```

**After**:
```markdown
execute_forgetful_tool("create_entity", {
    "name": "[entity name]",
    "entity_type": "[type]",
    "notes": "[description]"
})
```

## Next Steps

1. Create search-and-replace script or manual updates for each file
2. Verify changes don't break agent functionality
3. Run acceptance criteria tests
4. Commit changes with reference to #731
5. Update issue #731 status

## Time Estimate

- Per-file update: ~5-10 minutes (review context, replace patterns, verify)
- Total: ~2-3 hours for all 17 files
- Could be parallelized across multiple agents

## References

- Issue #731: https://github.com/rjmurillo/ai-agents/issues/731
- ADR-037: Memory Router Architecture
- Decision Matrix: AGENTS.md lines 108-127
