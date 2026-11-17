# memory-search

Searches project memory (Tier 1) for facts, patterns, and rules. It returns the relevant index and the atomic entries it links, so you read only what answers your question.

## When to use it

- You want to recall what the project already knows about a topic.
- You want prior context before you change existing code or architecture.
- Trigger phrases: `search memory`, `what do we know about X`, `recall prior context`.

## When not to use it

- You want to extract a session episode: use [`memory-reflexion`](memory-reflexion.md).
- You want to add citations: use [`memory-enhancement`](memory-enhancement.md).
- You want a multi-source gather across Serena, Context7, DeepWiki, and the web: use [`context-gather`](context-gather.md).

## Quick start

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:memory-search`. The agent loads it when your request matches, and [`autoplan`](autoplan.md) routes "what do we know about X" requests here. To ask for it by name, say:

```text
Use the memory-search skill to find what we know about git hooks.
```

The skill returns the matching index name and the memory entries it links, with sources.

## What you get

The search keyword-ranks Serena memory names, also searches the Tier 2 episode store, flags large memories by token estimate, and returns the relevant `*-index`. Read that index, then follow its links to the atomic file.

A search that matches nothing returns an empty result list plus a coverage note, not an error. Log a zero-result search as "no results". The skill reads committed markdown, so no service has to be up.

Progressive disclosure keeps cost low:

| Layer | Tool | Cost | When |
| --- | --- | --- | --- |
| Index | `search_memory.py` | about 100 to 500 tokens | Always start here. |
| Details | `read_memory` | about 500 to 10,000 tokens | After the index confirms relevance. |
| Deep dive | Follow cross-references | Variable | For complete understanding. |

## Advanced use

Run the script from the root of a checkout of this repository:

```bash
uv run python .claude/skills/memory/scripts/search_memory.py "git hooks" --max-results 5 --format json
```

| Flag | Meaning |
| --- | --- |
| `query` | Search query, 1 to 500 characters. |
| `--max-results` | 1 to 100. Default 10. |
| `--format` | `json` (default) or `table`. |
| `--serena-path` | Path to the Serena memories directory. |
| `--episodes-path` | Path to the Tier 2 episode store directory. |

For a scripted fallback, guess `read_memory("<intuitive-name>")` (a miss is a cheap "not found"), then the domain `*-index`, then `read_memory("memory-index")`. Prefer these over a bare `list_memories`.

| Symptom | Cause | Recovery |
| --- | --- | --- |
| Zero results | Query too narrow, or the index is empty | Broaden the terms and check the index. |
| Slow response | Large corpus | Lower `--max-results`. Every matched file is read for its preview. |
| Partial results | Token budget hit mid-retrieval | Read the coverage note and decide whether to continue. |

To add citations or confidence scoring, chain the output through [`memory-enhancement`](memory-enhancement.md). The script is shared with the [`memory`](memory.md) router, and this skill does not reimplement it. More detail is in [`references/skill-reference.md`](../../src/claude/skills/memory-search/references/skill-reference.md) and [`references/where-to-search.md`](../../src/claude/skills/memory-search/references/where-to-search.md).

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`memory`](memory.md): router for episode extraction, health, and maintenance.
- [`memory-enhancement`](memory-enhancement.md): citations and confidence on search results.
- [`curating-memories`](curating-memories.md): marks stale memories.
- [`autoplan`](autoplan.md): routes recall requests here.
- Source: [`SKILL.md`](../../src/claude/skills/memory-search/SKILL.md)
- Reference: [`quick-start.md`](../../src/claude/skills/memory-search/references/quick-start.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
