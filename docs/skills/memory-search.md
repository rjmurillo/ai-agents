# memory-search

Searches project memory (Tier 1) for facts, patterns, and rules. It reports relevant entries with their sources and any coverage gaps.

## When to use it

- You want to recall what the project already knows about a topic.
- You want prior context before you change existing code or architecture.
- Trigger phrases: `search memory`, `what do we know about X`, `recall prior context`.

## When not to use it

- You want to extract a session episode: use [`memory-reflexion`](memory-reflexion.md).
- You want to add citations: use [`memory-enhancement`](memory-enhancement.md).
- You want a multi-source gather across Serena, Context7, DeepWiki, and the web: use [`context-gather`](context-gather.md).

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:memory-search`. The agent loads it when your request matches, and [`autoplan`](autoplan.md) routes "what do we know about X" requests here. To ask for it by name, say:

```text
Use the memory-search skill to find what we know about git hooks.
```

Read the matching entries and verify their claims against current sources.

## What you get

The skill can use a project-scoped recall tool already available to your agent.
It checks local memory when the tool is unavailable or returns no relevant hits.

The bundled script ranks Markdown filenames and episode names by keyword.
Use the repository's established corpus or `.project-toolkit/memory/notes/`.
A search that finds zero entries still completes successfully.

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

Without the script, search the corpus by filename or consult its index.

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
