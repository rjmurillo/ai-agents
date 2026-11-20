# memory-maintenance

Runs health, size, and speed checks on the memory stores. It counts tokens, validates that memories stay atomic, suggests cross-links, and benchmarks search.

## When to use it

- You want to know which memory tiers are readable before a maintenance batch.
- You want the token cost of a memory before you retrieve it.
- You want to check that memory files stay small and focused.
- Trigger phrases: `check memory tier health`, `count memory tokens`, `benchmark memory performance`.

## When not to use it

- You want a Tier 1 search: use [`memory-search`](memory-search.md).
- You want to record a session: use [`memory-reflexion`](memory-reflexion.md).
- You want to mark content obsolete, deduplicate, or link: use [`curating-memories`](curating-memories.md).

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:memory-maintenance`. The agent loads it when your request matches, and [`curating-memories`](curating-memories.md) routes store checks here. To ask for it by name, say:

```text
Use the memory-maintenance skill to run a health check on the memory tiers and count tokens in .serena/memories/memory-index.md.
```

The skill runs the matching script and reports the result.

## What you get

| Operation | Result |
| --- | --- |
| Health check | `available: true` for each readable tier. `false` means a missing or unreadable directory. Every tier is local files, so it is not a service outage. |
| Token count | The file name and a token total. |
| Size validation | Exit 0 (pass) or 1 (fail) with a decomposition recommendation. |
| Benchmark | A latency report split into listing, matching, and reading phases. |
| Density dry run | Proposed links print and nothing is written. |

## Advanced use

Every operation calls a shared script from the [`memory`](memory.md) router. Run them from the root of a checkout of this repository:

```bash
uv run python .claude/skills/memory/scripts/test_memory_health.py --format table
uv run python .claude/skills/memory/scripts/count_memory_tokens.py .serena/memories/memory-index.md
uv run python .claude/skills/memory/scripts/test_memory_size.py .serena/memories --pattern "*.md"
uv run python .claude/skills/memory/scripts/measure_memory_performance.py --format console --iterations 5 --warmup 2
uv run python .claude/skills/memory/scripts/improve_memory_graph_density.py --dry-run
```

> [!WARNING]
> `invoke_memory_cross_reference.py` rewrites memory files and has no dry-run mode. It exits `0` even when a step fails, so read the `Errors` array in its JSON output. It exits `1` only when it finds no project root or the memories path is outside the project. A density dry run previews only one of its three steps, the related-links step. Run it only after a density dry run, then review its edits with `git diff --stat .serena/memories`.

| Script | Flags from `--help` |
| --- | --- |
| `test_memory_health.py` | `--format` (`json` or `table`), `--base-path` |
| `count_memory_tokens.py` | `-r`, `-c`, `-f`, `--pattern`, `--total`, `--limit` |
| `test_memory_size.py` | `-r`, `--pattern`, `--max-chars`, `--max-skills`, `--max-categories`, `-v`, `--fail-fast` |
| `measure_memory_performance.py` | `--queries`, `--iterations`, `--warmup`, `--format` (`console`, `markdown`, `json`), `--serena-path` |
| `improve_memory_graph_density.py` | `--dry-run`, `--memories-path`, `--files`, `--output-json` |
| `invoke_memory_cross_reference.py` | `--files`, `--memories-path`, `--output-json` |

Size thresholds for an atomic memory: at most 10,000 characters (about 2,500 tokens), 15 skills, and 5 categories. The token counter uses a SHA-256 hash cache, so the first run is slow and later runs are fast.

Density work is advisory. Run it with `--dry-run`, review the proposed links, then apply. Denser links help multi-hop retrieval, and over-dense linking adds noise.

Work in three steps: assess with the health check, measure with the operation you need, then act only after a dry run confirms the change and re-run the check.

| Symptom | Cause | Recovery |
| --- | --- | --- |
| A tier shows down | Store directory missing or unreadable | Verify the path exists. |
| Token count is slow | Cold cache on first run | Re-run. |
| Size validation fails | A memory passed the thresholds | Decompose it into atomic files. |
| Benchmark latency is high | Large corpus or many matched files | Read the per-phase split. |

Details are in [`references/benchmarking.md`](../../src/claude/skills/memory-maintenance/references/benchmarking.md) and [`references/troubleshooting.md`](../../src/claude/skills/memory-maintenance/references/troubleshooting.md).

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`memory`](memory.md): owns the scripts this skill runs.
- [`curating-memories`](curating-memories.md): content maintenance, and the skill that routes here.
- [`memory-consolidate`](memory-consolidate.md): merges files and tidies indexes.
- Source: [`SKILL.md`](../../src/claude/skills/memory-maintenance/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
