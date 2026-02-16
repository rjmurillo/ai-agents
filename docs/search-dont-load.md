# Search, Don't Load: Memory-First Evidence Protocol

> **Status**: Active
> **Related**: [ADR-007: Memory-First Architecture](../.agents/architecture/ADR-007-memory-first-architecture.md) |
> [SESSION-PROTOCOL.md](../.agents/SESSION-PROTOCOL.md) Phase 2

## What This Pattern Means

Agents search memory indexes before loading full memories. They never bulk-load
all memories into context. This keeps token budgets low and retrieval focused.

The pattern has three steps:

1. **Search** the `memory-index` for keywords matching your task.
2. **Select** only the memories that match.
3. **Load** those specific memories before reasoning about the task.

Without this pattern, agents either skip memories entirely (losing institutional
knowledge) or load too many (wasting tokens and diluting signal). Sessions that
skip memory loading show a 30% efficiency loss (see `init-003-memory-first-monitoring-gate`).

## Canonical Tool Calls

### Primary: Serena MCP (recommended)

```text
mcp__serena__read_memory("memory-index")
```

Read the index, identify rows matching your task keywords, then load each
matching memory:

```text
mcp__serena__read_memory("skills-pr-review-index")
mcp__serena__read_memory("ci-infrastructure-observations")
```

### Alternative: Slash Command

```text
/memory-search
```

Interactive search across all memory tiers. Good for exploratory queries.

### CLI: Python Script

```bash
python3 .claude/skills/memory/scripts/search_memory.py --query "pr review patterns"
```

Unified search across Serena and Forgetful with token budget warnings per ADR-037.

## Recording Evidence in Session Logs

The Session Start checklist requires evidence that memories were loaded. In your
session log's Protocol Compliance table, fill the Evidence column:

```markdown
| MUST | Read memory-index, load task-relevant memories | [x] | Loaded: skills-pr-review-index, ci-observations |
```

List the specific memory names you loaded. "Read memory-index" alone is
insufficient. The evidence must show which task-relevant memories you selected
and loaded.

### Good Evidence

- `Loaded: skills-pr-review-index, pr-comment-001-reviewer-signal-quality`
- `Loaded: ci-infrastructure-observations (only match for "CI runner" keywords)`

### Bad Evidence

- `Read memory-index` (no proof of selective loading)
- `Loaded all memories` (bulk loading, defeats the pattern)
- Empty (protocol violation)

## When to Use This Pattern

Every session start. The SESSION-PROTOCOL.md Phase 2 marks this as a **MUST**
requirement. Agents must read `memory-index` and load task-relevant memories
before modifying any code or files.

## References

- [ADR-007: Memory-First Architecture](../.agents/architecture/ADR-007-memory-first-architecture.md)
- [SESSION-PROTOCOL.md, Phase 2: Context Retrieval](../.agents/SESSION-PROTOCOL.md)
- [Memory Loading Protocol](../.agents/SESSION-PROTOCOL.md) (lines 112-123)
- Serena memory: `init-003-memory-first-monitoring-gate` (30% efficiency data)
