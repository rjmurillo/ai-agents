---
description: Research external topics, create comprehensive analysis, and incorporate learnings into memory systems
allowed-tools: [WebSearch, WebFetch, mcp__forgetful__*, mcp__serena__*, Skill]
model: opus
---

ultrathink

# Research and Incorporate Command

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
