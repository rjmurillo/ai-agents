# memory

Routes a memory request to the right focused sub-skill. It also saves verified facts to an authorized project store.

## When to use it

- You ask "what do we know about X", "recall prior context", or "search memory" and are not sure which memory operation you need.
- You want to retain a verified decision, result, or reusable lesson.
- Trigger phrases include `remember this`, `search memory`, `check memory tier health`, `extract episode from session`, `memory-first gate`, `consolidate memory`. A measured result that contradicts a memory routes to the `memory-gate` contradiction log.

## When not to use it

- You want to add citations to a memory: use [`memory-enhancement`](memory-enhancement.md).
- You want a narrative report across memory systems: use [`memory-documentary`](memory-documentary.md).
- You already know the operation: load the sub-skill directly (see the table below).

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:memory`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the memory skill to find what we recorded about the retry policy and tell me which memory operation to run next.
```

The skill picks a sub-skill with its decision tree and hands the work to it. When you are unsure, it starts with a Tier 1 search.

## What you get

A pointer to one of these sub-skills, then the sub-skill's result:

| You want to | Sub-skill |
| --- | --- |
| Find facts, patterns, or rules | [`memory-search`](memory-search.md) |
| Record a completed session as an episode | [`memory-reflexion`](memory-reflexion.md) |
| Check memory before changing an existing system (blocking) | [`memory-gate`](memory-gate.md) |
| Check health, count tokens, benchmark, or improve graph density | [`memory-maintenance`](memory-maintenance.md) |
| Do a periodic cleanup: merge overlaps and tidy the index | [`memory-consolidate`](memory-consolidate.md) |
| Mark in-file content obsolete | [`curating-memories`](curating-memories.md) |
| Gather deep multi-source context | [`context-gather`](context-gather.md) |

Episode extraction writes JSON files to `.project-toolkit/memory/episodes/`.

## Advanced use

Use a project-scoped tool already available to the agent when the destination
is clear. Otherwise use the established repository corpus or save a Markdown
note under `.project-toolkit/memory/notes/`. Name the topic, date, rationale,
and evidence. Check for an existing record before you write.

This repository keeps its corpus in `.serena/memories/`. Use file tools for
writes from a linked worktree. The Serena tool writes to its bound checkout.

When you add a row to a domain index file, insert it after the last data row, not after the header or the delimiter. Each observation carries `[YYYY-MM-DD] [Source]: content`. Conflicts get a new memory with a `supersedes` relation, and `[REVIEW]` when accuracy is uncertain.

The router owns the shared scripts. Run one from the root of a checkout of this repository:

```bash
uv run python .claude/skills/memory/scripts/search_memory.py "retry policy" --max-results 5 --format table
```

| Script | Purpose |
| --- | --- |
| `search_memory.py` | Search repository Markdown and the episode store. Flags: `--max-results` (1 to 100, default 10), `--format` (`json` or `table`), `--serena-path`, `--episodes-path`. |
| `count_memory_tokens.py` | Count tokens with tiktoken caching. Flags include `-r`, `--total`, `--limit`, `--force`. |
| `test_memory_size.py` | Validate memory atomicity. Flags include `--max-chars` (default 10,000), `--max-skills`, `--max-categories`. |
| `test_memory_health.py` | Health report. Flags: `--format` and `--base-path`. Exits 0 even when a tier is unavailable, so read the report. |
| `extract_session_episode.py` | Episode extraction, with `--validate`, `--fix`, and `--dry-run`. |
| `repair_episode_causal_links.py` | Restore causal edges in flattened episodes. |
| `migrate_causal_version.py` | One-shot migration that stamps `causal_order_version=2`. |
| `measure_memory_performance.py` | Serena search benchmark. |
| `improve_memory_graph_density.py` | Graph density improvement. |
| `convert_index_table_links.py`, `convert_memory_references.py` | Link conversion, each with `--dry-run`. |
| `invoke_memory_cross_reference.py` | Cross-reference memories. |

Both link converters share file processing and statistics through `memory_link_processing.py`.
The helper is internal, not another conversion command.

Run any script with `--help` for the exact flags.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`memory-search`](memory-search.md), [`memory-reflexion`](memory-reflexion.md), [`memory-gate`](memory-gate.md), [`memory-maintenance`](memory-maintenance.md), [`memory-consolidate`](memory-consolidate.md): the sub-skills this router points to.
- [`research`](research.md): redirects a search of this repository here.
- Source: [`SKILL.md`](../../src/claude/skills/memory/SKILL.md)
- Reference: [`tier-selection-guide.md`](../../src/claude/skills/memory/references/tier-selection-guide.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
