---
name: memory-search
version: 0.1.0
description: Tier 1 semantic memory search across the Serena corpus with
  progressive disclosure and token-budget warnings. The focused search operation
  split out of the memory router per ADR-063. Use when you say `search memory`,
  `what do we know about X`, or `recall prior context`. Do NOT use to extract
  session episodes or add citations (use memory or
  memory-enhancement).
license: MIT
metadata:
  adr: ADR-007, ADR-037, ADR-038, ADR-056, ADR-063
  type: operation
  parent: memory
---

# Memory Search

Tier 1 semantic search over memory: the focused search operation extracted from
the `memory` router per ADR-063 (memory-skill decomposition). `memory` still
routes here; a caller that needs only search loads this sub-skill instead of the
full memory surface.

## Triggers

Use this skill when the user says:

- `search memory` for semantic search across stored knowledge
- `what do we know about X` to recall facts, patterns, or constraints
- `recall prior context` before changing existing code or architecture

## Quick Start

```bash
# Search memory (Tier 1)
python3 .claude/skills/memory/scripts/search_memory.py "git hooks"

# JSON output for scripting
python3 .claude/skills/memory/scripts/search_memory.py "git hooks" --format json
```

The search script is canonical and shared with the `memory` router; this
sub-skill does not reimplement it. It lives at
`.claude/skills/memory/scripts/search_memory.py`.

## Quick Reference

| Operation | Script | Key Parameters |
|-----------|--------|----------------|
| Search facts/patterns | `search_memory.py` | `query`, `--max-results`, `--format` |

## Routing

`search_memory.py "<q>"` keyword-ranks Serena memory names, also searches the
Tier 2 episode store, flags large memories by token estimate, and returns the
relevant `*-index`. Read that index, then follow its links to
the atomic file.

Raw fallback when scripting: guess `read_memory("<intuitive-name>")` (a miss is
a cheap "not found", not a list), then the domain `*-index`, then
`read_memory("memory-index")`. Prefer these name and index lookups over a bare
`list_memories`.

## Progressive Disclosure

This skill implements progressive disclosure: list names, read details, deep
dive on cross-references. The point is to avoid loading a large memory when a
small slice answers the query.

| Layer | Tool | Cost | When to Use |
|-------|------|------|-------------|
| Index | `search_memory.py` | ~100-500 tokens | Always start here |
| Details | `read_memory` | ~500-10K tokens | After index confirms relevance |
| Deep Dive | Follow cross-references | Variable | For complete understanding |

Progressive disclosure prevents loading 9,500 tokens when only 1,200 are
relevant. List names first, then read only the entry the query needs.

## Graceful Degradation

Search degrades, it does not fail. Serena is the canonical store and travels
with the repository as plain markdown, so there is no service to be unreachable
and no fallback mode to select. A search that matches nothing returns an empty
result list plus a coverage note, never an error (ADR-007).

## Decision Tree

```text
What do you need?
│
├─► Current facts, patterns, or rules?
│   └─► search_memory.py "<query>"
│
└─► Not sure which tier?
    └─► Start here (Tier 1), escalate to the memory router if insufficient
```

## Verification

| Operation | Verification |
|-----------|--------------|
| Search completed | Result count > 0 OR logged "no results" |
| Empty corpus | Coverage note present; empty result list returned |

## Anti-Patterns

| Anti-Pattern | Do This Instead |
|--------------|-----------------|
| Skipping memory search | Always search before multi-step reasoning |
| Loading full memory eagerly | List names first, read only the relevant entry |
| Assuming a second backend exists | Serena is the only store; there is no semantic tier to fall back from |

## Process

### Phase 1: Query

Run `search_memory.py` with the query.

### Phase 2: Validate

Verify results are non-empty and relevant to the query context. A zero-result
search is a valid outcome; log it.

### Phase 3: Report

Return the relevant index name and the atomic entries it links, with source
attribution, to the caller.

## Related Skills

| Skill | When to Use Instead |
|-------|---------------------|
| `memory` | Router for episode extraction, health, or maintenance |
| `memory-enhancement` | Add citations, verify code references, track confidence |
| `curating-memories` | Memory maintenance (obsolete, deduplicate, link) |
| `exploring-knowledge-graph` | Multi-hop graph traversal beyond Tier 1 search |

## Troubleshooting

| Symptom | Cause | Recovery |
|---------|-------|----------|
| Zero results | Query too narrow or memory index empty | Broaden query terms; verify memory index contains relevant entries |
| Slow response | Large memory corpus | Lower `--max-results`; every matched file is read for its preview |
| Partial results | Token budget hit mid-retrieval | Results include coverage note; caller decides whether to continue |

## Extension Points

| Extension | How to Add |
|-----------|------------|
| New memory tier | Create sibling sub-skill (e.g., `memory-episode`); register in `memory` router |
| Custom search backend | Implement script matching `search_memory.py` interface; update skill to invoke |
| Result post-processing | Chain output through `memory-enhancement` for citations or confidence scoring |

## References

- ADR-007: Memory system architecture
- ADR-037: Memory tier boundaries
- ADR-038: Episodic memory structure
- ADR-056: Memory progressive disclosure
- ADR-063: Memory skill decomposition (this extraction)

These reference files travel with the search operation per ADR-063. They are
demand-loaded; read one when you need the detail it covers.

| Document | Content |
|----------|---------|
| [references/quick-start.md](references/quick-start.md) | Common search and usage workflows |
| [references/memory-router.md](references/memory-router.md) | ADR-037 router architecture behind `search_memory.py` |
| [references/api-reference.md](references/api-reference.md) | Complete function reference for the memory API |
| [references/skill-reference.md](references/skill-reference.md) | Detailed `search_memory.py` script parameters |
