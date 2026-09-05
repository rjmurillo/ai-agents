---
name: memory
version: 0.4.0
description: Thin router for the tiered memory system. Points callers at the
  focused sub-skills for each operation, Tier 1 search, the reflexion write path,
  the memory-first gate, maintenance, and consolidation. Use when you ask "what
  do we know about X", "recall prior context", or "search memory" and are not
  sure which operation you need. Do NOT use for adding citations (use
  memory-enhancement) or narrative cross-system reports (use memory-documentary).
license: MIT
metadata:
  adr: ADR-037, ADR-038, ADR-063
  timelessness: 8/10
---
# Memory System Skill

Thin router across the tiered memory system. Each operation lives in a focused
sub-skill (ADR-063 memory-skill decomposition); this router points you at the
right one so a caller loads only the surface it needs.

---

## When to Use This Skill

| Scenario | Use Memory Router? | Alternative |
|----------|-------------------|-------------|
| Not sure which memory operation you need | Yes | - |
| Tier 1 search only | No | `memory-search` sub-skill |
| Record a completed session | No | `memory-reflexion` sub-skill |
| Pre-change memory-first gate | No | `memory-gate` sub-skill |
| Health, token count, benchmark | No | `memory-maintenance` sub-skill |
| Periodic durable/dated consolidation, index tidy | No | `memory-consolidate` sub-skill |
| Agent needs deep context | No | `exploring-knowledge-graph` skill |
| Human at CLI | No | `/memory-search` command |

See the [exploring-knowledge-graph skill](../exploring-knowledge-graph/SKILL.md)
for the deep-context decision tree and the five-source strategy (Issue #2103
folded the former context-retrieval agent into it).

---

## Related Sub-Skills

The router delegates every operation to a focused sub-skill. Load the one that
matches your task; each carries a smaller context than the full memory surface.

| Sub-Skill | Operation | Load When |
|-----------|-----------|-----------|
| `memory-search` | Tier 1 semantic search (Serena) | You need facts, patterns, or rules |
| `memory-reflexion` | Tier 2 episode extraction | You are recording a completed session |
| `memory-gate` | Memory-First Gate (BLOCKING) and Chesterton's Fence protocol | You are about to change an existing system |
| `memory-maintenance` | Health check, token count, size validation, benchmark, density | You are maintaining the memory stores |
| `memory-consolidate` | Periodic durable/dated consolidation, overlap merge, index tidy | You are doing a periodic memory cleanup pass |

---

## Triggers

Use this skill when the user says:

- `search memory` for semantic search across tiers (routes to memory-search)
- `check memory health` for system status (routes to memory-maintenance)
- `extract episode from session` for session replay (routes to memory-reflexion)
- `memory-first gate` before changing an existing system (routes to memory-gate)
- `consolidate memory` for a periodic durable/dated review and index tidy (routes to memory-consolidate)

---

## Decision Tree

```text
What do you need?
│
├─► Current facts, patterns, or rules?
│   └─► memory-search sub-skill (Tier 1)
│
├─► About to change existing code, a constraint, or a protocol?
│   └─► memory-gate sub-skill (search the "why" first, BLOCKING)
│
├─► Record what happened in a completed session?
│   └─► memory-reflexion sub-skill (Tier 2 episode extraction)
│
├─► Store new factual knowledge directly?
│   └─► Write a Serena memory (mcp__serena__write_memory), then
│       curating-memories to keep it accurate
│
├─► Check health, count tokens, benchmark, or improve graph density?
│   └─► memory-maintenance sub-skill
│
├─► Periodic pass: separate durable from dated, merge overlaps, tidy the index?
│   └─► memory-consolidate sub-skill
│
└─► Not sure which tier?
    └─► Start with memory-search (Tier 1), escalate if insufficient
```

For deeper guidance on picking a tier, see
[references/tier-selection-guide.md](references/tier-selection-guide.md).

---

## Progressive Disclosure

The memory system uses progressive disclosure: list names, read details, deep
dive on cross-references. This prevents loading a large memory when a small slice
answers the query (up to an 87% token reduction). The `memory-search` sub-skill
owns the Tier 1 index-then-read flow; start there.

Atomic files plus indexes are deliberate: there are no embeddings, so the
filename is the activation vocabulary. Do NOT consolidate atomic memories to
cheapen listing; it breaks discovery and cross-links. On add, update the domain
`*-index` so the next agent finds the memory by name.

---

## Serena Write Conventions

These conventions govern writing a new Serena memory and registering it in its
domain index. They are the load-bearing rules absorbed from the former `memory`
agent (Issue #2102). For obsolete-marking, deduplication, and bidirectional
linking, use the `curating-memories` skill.

### Naming

- File name: `[domain]-[descriptive-name].md`, lowercase with hyphens (for
  example `pr-review-security.md`).
- Entity ID inside the file: `{domain}-{description}`, kebab-case, no prefix
  (for example `pr-enum-001`). File name and entity ID are separate; do not
  conflate them.

### Index-Table Insertion (hazard)

Domain index files (`skills-*-index.md`) contain ONLY a two-column table. When
you add a memory you MUST insert AFTER the last existing DATA row, never after
the header or the delimiter:

```text
| Keywords | File |    <-- header row
|----------|------|    <-- delimiter row (SKIP THIS)
| existing | file |    <-- data rows; insert after the LAST one
```

Inserting after the header or delimiter corrupts the table and breaks name-based
discovery for every reader. Do not add titles, statistics, or prose to an index
file.

### Relations (encoded in the memory body)

```markdown
## Relations

- **supersedes**: [previous-file-name]
- **depends_on**: [dependency-file-name]
- **related_to**: [related-file-name]
```

`supersedes` (new version replaces old), `depends_on` (requires another memory),
`related_to` (loose association).

### Source Tracking (required on every observation)

```text
[YYYY-MM-DD] [Source]: [Observation content]
```

Source forms: `[agent-name]`, `[doc:path]`, `[decision:ADR-NNN]`, `[user]`,
`[ext:source]`. Reasoning over actions: record WHY a choice was made, not just
WHAT was done.

### Conflict Resolution

When observations contradict, prefer the most recent, create a new memory with a
`supersedes` relation, and prefix with `[REVIEW]` when accuracy is uncertain.

---

## Storage Locations

| Data | Location |
|------|----------|
| Serena memories | Serena memory store (travels with the repository) |
| Episodes | Local episode store (see `memory-reflexion`) |

---

## Anti-Patterns

| Anti-Pattern | Do This Instead |
|--------------|-----------------|
| Skipping the memory-first gate | Route to `memory-gate` before changing existing systems |
| Loading the full router for one operation | Load the focused sub-skill instead |
| Tier confusion | Follow the decision tree; start at Tier 1 |
| Consolidating atomic memories | Keep one concept per file; update the index on add |

---

## See Also

Router-owned references, shared across the memory sub-skills. Operation-specific
references travel with their sub-skill (ADR-063).

| Document | Content |
|----------|---------|
| [tier-selection-guide.md](references/tier-selection-guide.md) | When to use each tier |
| [zettelkasten-memory-agents.md](references/zettelkasten-memory-agents.md) | Atomic memory principle and auto-linking |
| [codebase-knowledge-graph.md](references/codebase-knowledge-graph.md) | GitNexus pattern for structural context via MCP |

---

## Verification

| Operation | Verification |
|-----------|--------------|
| Routed to sub-skill | Sub-skill SKILL.md loaded and its verification gate applied |
| Search completed | Result count > 0 OR logged "no results" |
| Episode extracted | JSON file in `.agents/memory/episodes/` |
| Health check | All tiers show "available: true" |

Verification checklist:

- [ ] Correct sub-skill selected from the decision tree
- [ ] Operation ran through the sub-skill, not inline in the router

---

## Process

### Phase 1: Route

Match the request to a sub-skill using the decision tree and When-to-Use matrix.

### Phase 2: Delegate

Load the selected sub-skill and run its operation against the canonical scripts.

### Phase 3: Report

Return structured results to the caller with source attribution.

---

## Scripts

The router owns the canonical memory scripts. Sub-skills delegate to these paths
(ADR-063); the router does not duplicate them.

| Script | Purpose | Exit Codes |
|--------|---------|------------|
| `search_memory.py` | Search across Serena and the episode store | 0=success, 1=error |
| `count_memory_tokens.py` | Token counting with tiktoken caching | 0=success, 1=error |
| `test_memory_size.py` | Memory atomicity validation | 0=pass, 1=violations |
| `test_memory_health.py` | System health dashboard | 0=success |
| `extract_session_episode.py` | Episode extraction; `--validate` checks the store at rest, `--fix` repairs backwards commit order | 0=success, 1=error, 2=violation or bad flag |
| `repair_episode_causal_links.py` | Restore causal edges in flattened episodes | 0=success, 1=an episode is invalid, 2=episodes dir missing |
| `migrate_causal_version.py` | One-shot migration: stamps `causal_order_version=2` on legacy episodes (#3598); `--dry-run` previews counts without writing | 0=all stamped, 1=some skipped, 2=bad path |
| `measure_memory_performance.py` | Serena search benchmark, by phase | 0=success, 1=error |
| `improve_memory_graph_density.py` | Graph density improvement | 0=success, 1=error |
| `convert_index_table_links.py` | Index table link conversion | 0=success, 1=error |
| `invoke_memory_cross_reference.py` | Cross-reference memories | 0=success, 1=error |

Invoke via the portable root form:

```bash
"${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/test_memory_health.py" --format table
```

---

## Related Skills

| Skill | When to Use Instead |
|-------|---------------------|
| `memory-search` | Tier 1 search only; smaller context than the router (ADR-063) |
| `memory-reflexion` | Tier 2 episode extraction (ADR-063) |
| `memory-gate` | Memory-First Gate and Chesterton's Fence protocol (ADR-063) |
| `memory-maintenance` | Health, token count, size, benchmark, density (ADR-063) |
| `memory-consolidate` | Periodic durable/dated consolidation, merge, index tidy |
| `memory-enhancement` | Add citations, verify code references, track confidence |
| `memory-documentary` | Narrative cross-system memory reports |
| `curating-memories` | Memory content maintenance (obsolete, deduplicate) |
| `exploring-knowledge-graph` | Multi-hop graph traversal |

<!-- vendor-portability: declared. This skill links reference docs that ship in its own references/ tree and routes callers to sibling sub-skills. The episode store is the consumer's own data dir, created on demand when absent in a vendored install. Issue #2050, ADR-063. -->
