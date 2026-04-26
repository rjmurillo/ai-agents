---
description: Generate evidence-based documentary reports by searching across all memory systems
argument-hint: <topic>
allowed-tools: mcp__forgetful__*, mcp__serena__*, mcp__context7__*, WebSearch, Grep, Glob, Read, Skill
model: opus
---

# Memory Documentary

ultrathink

Generate evidence-based documentary reports by searching across all memory systems.

## Usage

```bash
/memory-documentary [topic]
```

## Arguments

- `topic` (required): The subject to analyze across memory systems

## Examples

```bash
/memory-documentary "recurring frustrations"
/memory-documentary "coding patterns not codified"
/memory-documentary "evolution of thinking on testing"
/memory-documentary "decisions I second-guessed"
```

## Execution

This command invokes the memory-documentary skill which:

1. Searches ALL 4 MCP servers (Claude-Mem, Forgetful, Serena, DeepWiki)
2. Searches .agents/ directory artifacts
3. Searches docs/ directory artifacts
4. Searches GitHub issues (open and closed)
5. Searches GitHub pull requests (open and closed)
6. Generates documentary-style report with full evidence chains
7. Updates memories with discovered meta-patterns

## Budget

Max 30k output tokens. Prioritize depth over breadth. Cap each source to at most 25 top-ranked results; stop traversing a source once diminishing returns appear (3 consecutive results add no new evidence).

## Stop Criteria

Complete when ALL of the following are true:

1. All 4 MCP servers have been searched (or skipped with reason recorded).
2. GitHub issues and PRs have been searched (or skipped with reason recorded).
3. `.agents/` and `docs/` artifacts have been searched.
4. The report has been written to the output path below.
5. Memories have been updated with discovered meta-patterns.

Do NOT continue searching after these conditions are met. If a source is unavailable, skip it and record the skip in the Sources section of the report.

## Output Format

Report saved to: `.agents/analysis/[topic]-documentary-[date].md`

Required sections (in this order):

1. **Executive Summary**: 3 to 5 bullets. The thesis in under 150 words.
2. **Evidence Chain**: chronological or thematic findings. Each claim cites a source (file path, memory ID, issue or PR number, commit SHA).
3. **Sources**: table of sources queried, status (searched, skipped, unavailable), and result counts.
4. **Meta-patterns**: cross-source patterns (minimum 1, maximum 7). Each pattern lists supporting evidence IDs.
5. **Gaps**: what could not be answered, why, and what would be needed.

Report length target: 2k to 6k words. Hard cap: 30k output tokens total across all tool calls and the final report.

If search results are overwhelming (more than 100 per source), tighten the query and report only the top 25 per source in the Evidence Chain. If results are sparse (fewer than 5 total), say so in the Executive Summary and keep the report short rather than padding.

## Fallback Rules

- **MCP server unavailable** (Claude-Mem, Forgetful, Serena, DeepWiki): skip that source, continue with remaining sources, and note the skip in the Sources section with a one-line reason.
- **GitHub API rate limit** hit: stop GitHub searches, record partial results in Sources with status `rate-limited`, and proceed to synthesis with what was gathered.
- **Zero results** for the topic across all sources: abort the report, write a single-page note at the output path explaining what was searched and that no evidence was found. Do not fabricate findings.
- **Tool error** on any single call: retry once. If the second call fails, mark the source `error` in Sources and continue.

## Related Commands

- `/memory-search` - Simple memory search
- `/memory-explore` - Knowledge graph traversal
