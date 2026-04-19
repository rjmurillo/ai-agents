---
description: Research external topics, create comprehensive analysis, and incorporate learnings into memory systems
allowed-tools: WebSearch, WebFetch, mcp__forgetful__*, mcp__serena__*, Skill
model: opus
---

# Research and Incorporate Command

ultrathink

Research external topics, create comprehensive analysis, and incorporate learnings into memory systems.

## Usage

```text
/research

Topic: {topic name}
Context: {why this matters to the project}
URLs: {optional comma-separated source URLs}
```

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `Topic` | Yes | Subject to research |
| `Context` | Yes | Why this matters to the project |
| `URLs` | No | Source URLs to fetch and analyze |

## Example

```text
/research

Topic: Chesterton's Fence
Context: Decision-making principle for understanding existing systems before changing them
URLs: https://fs.blog/chestertons-fence/, https://en.wikipedia.org/wiki/G._K._Chesterton
```

## What This Does

1. **Research Phase**: Check existing knowledge, fetch URLs, perform web searches
2. **Analysis Phase**: Write 3000-5000 word analysis to `.agents/analysis/`
3. **Applicability Phase**: Map integration points with ai-agents project
4. **Memory Phase**: Create Serena memory + 5-10 atomic Forgetful memories
5. **Action Phase**: Create GitHub issue if implementation work identified

## Budget

Complete within 50k output tokens. If approaching the limit, summarize findings so far, persist partial analysis, and stop. Prefer completing fewer phases well over partial work across all phases.

## Fallback Rules

- If `WebSearch` returns no results for a query, try 2 alternative phrasings, then proceed with available information.
- If a `WebFetch` URL is unreachable or returns a non-success status, note it as unavailable in the analysis and continue with other sources.
- If memory systems (Serena or Forgetful) are unavailable, skip the Memory Phase and record the skip in the Action Phase output.

## Stop Conditions

Stop when any of the following is true:

- All 5 phases completed.
- 3 phases have failed (treat an intentional skip under a Fallback Rule as not-failed).
- The 50k output-token budget is reached.

## Output

| Artifact | Location |
|----------|----------|
| Analysis document | `.agents/analysis/{topic-slug}.md` |
| Serena memory | `.serena/memories/{topic-slug}-integration.md` |
| Forgetful memories | 5-10 atomic memories in knowledge graph |
| GitHub issue | Created if implementation work identified |

## Related

- Skill: `.claude/skills/research-and-incorporate/SKILL.md`
- Memory skill: `/memory-search` for retrieving incorporated knowledge
