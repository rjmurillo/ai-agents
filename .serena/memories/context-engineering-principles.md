# Context Engineering Principles

**Date**: 2026-02-09
**Source**: claude-mem.ai, Anthropic engineering blog, Vercel research
**Confidence**: HIGH (quantitative evidence from multiple sources)

## Core Principle

Find the smallest set of high-value tokens that maximize desired outcomes. Context is finite; every token attends to every other token (n^2 relationships), causing accuracy decline as context grows.

## Three-Layer Progressive Disclosure

| Layer | Token Cost | Purpose |
|-------|------------|---------|
| Index | ~800 | Titles, timestamps, token counts |
| Details | 50-500/item | Full content on-demand |
| Deep Dive | Variable | Original sources when needed |

Traditional RAG wastes ~94% attention on irrelevant context. Progressive disclosure achieves near-100% relevance.

## Just-In-Time Retrieval

```text
Search (Index) -> Review Results -> Fetch Selected
```

- Maintain lightweight identifiers (paths, queries, links)
- Load dynamically at runtime
- Avoid context pollution
- Enable progressive discovery

**Token savings**: 10 search results ~1,000 tokens vs 20 full observations 10,000-20,000 tokens (~10x efficiency).

## System Prompt Design

Balance between:
- Overly brittle (hardcoded logic that breaks)
- Overly vague (no actionable signals)

Ideal: "specific enough to guide behavior effectively, yet flexible enough to provide strong heuristics."

## Quantitative Evidence

From Vercel research:

| Approach | Pass Rate |
|----------|-----------|
| Baseline | 53% |
| Skills + instructions | 79% |
| AGENTS.md passive | 100% |

Key insight: information present every turn without decision points is used reliably.

## Anti-Patterns

1. Context cramming (n^2 cost)
2. Brittle conditional logic
3. Bloated tool sets
4. Exhaustive edge case lists
5. Assuming larger windows solve rot
6. Ignoring pollution over time
7. Late retrieval (after decisions)

## Project Application

| Pattern | ai-agents Status |
|---------|-----------------|
| CLAUDE.md under 100 lines | Aligned |
| Progressive disclosure | Partial (skills) |
| Serena atomic memories | Aligned |
| Just-in-time retrieval | Aligned |

## Analysis

Full analysis: `.agents/analysis/context-engineering.md`

## Related

- [memory-token-efficiency](memory-token-efficiency.md)
- [retrieval-led-reasoning-2026-02-08](retrieval-led-reasoning-2026-02-08.md)
- [passive-context-vs-skills-vercel-research](passive-context-vs-skills-vercel-research.md)
- [artifact-token-efficiency](artifact-token-efficiency.md)
- [memory-index](memory-index.md)
