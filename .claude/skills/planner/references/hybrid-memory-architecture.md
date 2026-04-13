---
source: wiki/concepts/AI Productivity/Hybrid Memory Architecture for AI Agents.md
created: 2026-04-11
review-by: 2026-07-11
---

# Hybrid Memory Architecture

80% of memory queries are structured lookups (entity, key, value), not fuzzy semantic queries. Match query type to storage type.

## Storage Selection

| Query Type | Example | Best Tool |
|------------|---------|-----------|
| Exact fact | "What is X's birthday?" | SQLite + FTS5 (instant, free) |
| Fuzzy/contextual | "What did we discuss about infra last week?" | Vector search |
| Always-available | Identity, API keys, active projects | MEMORY.md (always in context) |

## Hybrid Retrieval Cascade

```
Message arrives
  -> SQLite FTS5 search (instant, zero cost)
  -> Vector search (~200ms, one embedding call)
  -> Merge, deduplicate, composite score
  -> Inject top results into context
```

Composite score: BM25 x 0.6 + freshness x 0.25 + confidence x 0.15

## Memory Decay Tiers

| Tier | Examples | TTL |
|------|----------|-----|
| Permanent | Names, API endpoints, architecture decisions | Never |
| Stable | Project details, tech stack | 90 days (resets on access) |
| Active | Current tasks, sprint goals | 14 days (resets on access) |
| Session | Debugging context, temp state | 24 hours |
| Checkpoint | Pre-flight saves | 4 hours |

TTL refreshes on access. Frequency of access signals continued relevance.

## Decision Extraction

Decisions get permanent decay class. Auto-extract from patterns:

- "We decided X because Y" -> entity: decision, key: X, value: Y
- "Always/never do X" -> entity: convention, key: X, value: always/never

Decisions with rationale (the why alongside the what) are reusable when the agent encounters similar questions later.

## Pre-Flight Checkpoints

Before risky operations, save: intent, current state, expected outcome, files being modified. Auto-expires after 4 hours. Survives context compression. This is a write-ahead log for agent memory.

## Planning Implications

1. Start with SQLite + FTS5, not vectors (covers 80%, zero cloud dependency)
2. Design decay tiers from day one (retrofitting requires migration)
3. Extract decisions explicitly and immediately (highest value, easiest to skip)
