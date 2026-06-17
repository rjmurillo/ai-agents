---
name: memory-search
version: 0.1.0
description: Tier 1 semantic memory search across Serena and Forgetful with
  progressive disclosure and token-budget warnings. The focused search operation
  split out of the memory router per ADR-063. Use when you say `search memory`,
  `what do we know about X`, or `recall prior context`. Do NOT use to extract
  session episodes, update the causal graph, or add citations (use memory or
  memory-enhancement).
license: MIT
model: claude-sonnet-4-6
metadata:
  adr: ADR-007, ADR-037, ADR-063
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

# Lexical-only fallback when Forgetful is unreachable
python3 .claude/skills/memory/scripts/search_memory.py "git hooks" --lexical-only

# JSON output for scripting
python3 .claude/skills/memory/scripts/search_memory.py "git hooks" --format json
```

The search script is canonical and shared with the `memory` router; this
sub-skill does not reimplement it. It lives at
`.claude/skills/memory/scripts/search_memory.py`.

## Quick Reference

| Operation | Script | Key Parameters |
|-----------|--------|----------------|
| Search facts/patterns | `search_memory.py` | `query`, `--lexical-only`, `--max-results`, `--format` |

## Routing

`search_memory.py "<q>"` keyword-ranks Serena memory names (Serena-first,
augments with Forgetful when reachable, flags large memories by token estimate)
and returns the relevant `*-index`. Read that index, then follow its links to
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

Search degrades, it does not fail. When Forgetful is unreachable, pass
`--lexical-only` to run Serena-only lexical search. Serena is the canonical
store and travels with the repository; Forgetful is supplementary and local.
A search that loses Forgetful returns Serena results plus a coverage note, never
an error (ADR-007).

## Decision Tree

```text
What do you need?
│
├─► Current facts, patterns, or rules?
│   └─► search_memory.py "<query>"
│
├─► Forgetful unreachable?
│   └─► search_memory.py "<query>" --lexical-only
│
└─► Not sure which tier?
    └─► Start here (Tier 1), escalate to the memory router if insufficient
```

## Verification

| Operation | Verification |
|-----------|--------------|
| Search completed | Result count > 0 OR logged "no results" |
| Forgetful degraded | Coverage note present; Serena results returned |

## Anti-Patterns

| Anti-Pattern | Do This Instead |
|--------------|-----------------|
| Skipping memory search | Always search before multi-step reasoning |
| Loading full memory eagerly | List names first, read only the relevant entry |
| Forgetful hard dependency | Use `--lexical-only` fallback |

## Process

### Phase 1: Query

Run `search_memory.py` with the query. Choose `--lexical-only` when Forgetful is
known unreachable.

### Phase 2: Validate

Verify results are non-empty and relevant to the query context. A zero-result
search is a valid outcome; log it.

### Phase 3: Report

Return the relevant index name and the atomic entries it links, with source
attribution, to the caller.

## Related Skills

| Skill | When to Use Instead |
|-------|---------------------|
| `memory` | Router for episode extraction, causal graph, health, or maintenance |
| `memory-enhancement` | Add citations, verify code references, track confidence |
| `curating-memories` | Memory maintenance (obsolete, deduplicate, link) |
| `exploring-knowledge-graph` | Multi-hop graph traversal beyond Tier 1 search |
