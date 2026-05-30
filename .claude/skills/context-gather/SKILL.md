---
name: context-gather
version: 1.0.0
model: claude-sonnet-4-6
description: Gather comprehensive context from Forgetful Memory, Context7 docs, DeepWiki, and web sources before planning or implementation. Delegates to the context-retrieval subagent to search across all knowledge tiers and returns a focused summary with a parseable CONTEXT_LOADED marker for downstream skip detection.
license: MIT
---

# Context Gather

Collect multi-source context before planning or implementation. Searches Forgetful Memory, Serena, Context7, DeepWiki, and web sources, then returns a focused summary that downstream commands can detect and skip redundant fetches.

> **Model choice (behavior change from prior `/context-gather` slash command)**: this skill declares `model: claude-sonnet-4-6`, downgraded from the slash command's `opus`. Context retrieval is search-and-synthesis work, not deep reasoning; the cost-appropriate tier per ADR-002 model selection is sonnet. Skill behavior is otherwise unchanged.

## Triggers

| Phrase | Context |
|--------|---------|
| `gather context for` | User requests pre-work context collection |
| `context-gather` | Direct skill invocation or programmatic call from build, plan, research commands (SPEC-005) |
| `what do we know about` | Exploratory context retrieval |

## Quick Reference

| Field | Value |
|-------|-------|
| Input | Task description or technology topic (free text) |
| Output | Focused summary with code snippets, architectural insights, and `CONTEXT_LOADED: <topic>` marker |
| Quality Gate | Summary addresses the stated topic; at least two knowledge tiers queried; marker line present |

## When to Use

Use this skill when:

- Starting a complex task that needs multi-source context before planning or implementation.
- A lifecycle command (`/build`, `/plan`, `/research`) triggers preflight context loading.
- You need to pull framework-specific guidance from Context7 alongside project memory.
- Exploring what the knowledge graph knows about a topic before committing to an approach.

## When to Skip

Skip this skill when:

- A `CONTEXT_LOADED: <topic>` marker for the same topic already exists in the current conversation. Do not re-fetch.
- The task is trivial and single-step (no external context needed).
- You already have sufficient context from a prior skill invocation or manual research.
- The topic is purely internal to the current file (no cross-cutting concerns).

## Process

### Phase 1: Check for Prior Invocation

1. Scan the current conversation for an existing `CONTEXT_LOADED:` marker line.
2. If a marker exists whose topic matches the current request, report "Context already loaded for <topic>" and stop. Do not re-fetch.

### Phase 2: Delegate to Context-Retrieval Subagent

1. Invoke the `context-retrieval` subagent with the task description.
2. The subagent executes the following searches in parallel where possible:
   - **Forgetful Memory**: Search across ALL projects for relevant patterns, decisions, and code artifacts.
   - **Serena Memory**: Read linked entities, observations, and relations for the topic.
   - **Context7**: Query framework-specific documentation if the topic involves a known library or SDK.
   - **DeepWiki**: Read repository-level documentation for relevant GitHub repos.
   - **Web Search**: Fall back to web sources only when memory and docs are insufficient.
3. Wait for the subagent to return its findings.

### Phase 3: Synthesize, Emit Marker, and Return

1. Combine findings into a focused summary. Include:
   - Relevant code snippets and file paths.
   - Architectural insights and ADR references.
   - Framework-specific guidance (if applicable).
   - Gaps or unknowns that remain.
2. Emit the marker line at the end of the summary output:

```text
CONTEXT_LOADED: <topic>
```

Where `<topic>` is a short, normalized label for the subject (e.g., `pytest-fixtures`, `session-protocol`, `react-server-components`).

3. Return the summary and marker to the calling command or user. Downstream callers (`/build`, `/plan`, `/research` per SPEC-005) detect the marker and skip redundant context fetches.

## Extension Points

1. **Additional knowledge tiers**: new MCP servers (e.g., a future code-search server) slot into Phase 2 without changing the skill structure.
2. **Marker protocol**: the `CONTEXT_LOADED:` format can be extended with metadata (e.g., `CONTEXT_LOADED: <topic> [tier=serena,context7]`) to convey which sources were queried.

## Tools

This skill delegates to the context-retrieval subagent, which uses:

- `mcp__serena__read_memory`, `mcp__serena__list_memories`
- `mcp__claude_ai_Context7__resolve-library-id`, `mcp__claude_ai_Context7__query-docs`
- `mcp__deepwiki__read_wiki_structure`, `mcp__deepwiki__read_wiki_contents`, `mcp__deepwiki__ask_question`
- `WebSearch`, `WebFetch`

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Re-fetching when marker exists | Wastes tokens and time; duplicates context | Check for `CONTEXT_LOADED:` marker first |
| Querying all sources sequentially | Slow; unnecessary when early sources suffice | Query in parallel; stop early if coverage is sufficient |
| Returning raw tool output | Floods context window; not actionable | Synthesize into a focused summary with citations |
| Skipping the marker emission | Downstream commands cannot detect prior invocation | Always emit `CONTEXT_LOADED: <topic>` at the end |
| Using opus model for retrieval | Context gathering is search and synthesis, not deep reasoning | Use sonnet (cost-appropriate) |

## Verification

After execution, confirm:

- [ ] Reconciliation: `grep -c '^TIER_QUERIED:' <output>` >= 2 (emit one `TIER_QUERIED: <tier>` line per source actually queried, e.g. `TIER_QUERIED: Serena`, `TIER_QUERIED: Context7`)
- [ ] `CONTEXT_LOADED: <topic>` marker line is present at the end of output.
- [ ] Summary addresses the stated topic with specific findings, not generic advice.
- [ ] No raw tool output was returned; findings are synthesized.
- [ ] If a prior marker existed for the same topic, the skill short-circuited without re-fetching.

## References

| Artifact | Relationship |
|----------|-------------|
| SPEC-005 REQ-005 | Acceptance criteria AC-12 defines runtime-conditional skip via `CONTEXT_LOADED:` marker |
| SPEC-005 DESIGN-005 | Per-command edit specs reference context-gather as preflight dependency |
| `.claude/skills/reflect/SKILL.md` | Downstream consumer that may benefit from context loaded in this skill |
| `.claude/skills/steering-matcher/SKILL.md` | Sibling preflight skill in the `/build` chain |
| `.claude/skills/chestertons-fence/SKILL.md` | Sibling preflight skill in the `/build` chain |
