# Skill-Documentation-003: Fallback Preservation

## Statement

Include fallback clause when migrating to tool calls for graceful degradation

## Context

When abstracting direct file access to tool calls

## Evidence

Session 26 (2025-12-18): 5 fallback clauses added during Serena memory reference migration (e.g., "If Serena MCP not available, then...")

## Metrics

- Atomicity: 96%
- Impact: 9/10
- Category: documentation-maintenance, migration, resilience
- Created: 2025-12-18
- Tag: helpful
- Validated: 1

## Related Skills

- Skill-Documentation-001 (Systematic Migration Search)
- Skill-Documentation-002 (Reference Type Taxonomy)

## Fallback Pattern

**Before (direct file access only)**:

```markdown
The agent MUST read .serena/memories/skill-usage-mandatory.md before proceeding.
```

**After (tool call with fallback)**:

```markdown
The agent MUST read the skill-usage-mandatory memory using `mcp__serena__read_memory` with `memory_file_name="skill-usage-mandatory"`.
  - If the Serena MCP is not available, then the agent MUST read `.serena/memories/skill-usage-mandatory.md`
```

## Fallback Scenarios

| Primary Method | Fallback | Use Case |
|----------------|----------|----------|
| MCP tool call | Direct file path | MCP server not running |
| API endpoint | Local file cache | Network unavailable |
| Database query | JSON file | Database connection failed |
| Remote service | Static config | Service outage |

## Key Principles

1. **Graceful Degradation**: System works at reduced capability, not failure
2. **Explicit Fallback**: Document fallback path, don't assume agents will infer
3. **Testable**: Both primary and fallback paths should be testable
4. **Maintain Parity**: Fallback provides same information (may be slower/less convenient)

## Anti-Pattern

Tool-only reference without fallback:

```markdown
Use mcp__serena__read_memory to access skills
```

**Problem**: If MCP unavailable, agent has no guidance on fallback method

## Success Criteria

- Every tool call migration includes fallback clause
- Fallback provides equivalent functionality (reads same data)
- Conditional syntax clear: "If [tool] not available, then [fallback]"
- Both paths documented and testable
