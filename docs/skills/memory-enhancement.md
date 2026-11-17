# memory-enhancement

Manages citations in Serena memories. It checks that the code a memory points to still exists, scores how far to trust each memory, and reports which memories went stale.

## When to use it

- You want to link a memory to a file, function, issue, PR, ADR, memory, or URL.
- You want to check that a memory's code references are still valid.
- You want a staleness report across all memories.
- Trigger phrases: `add citation to memory`, `verify memory citations`, `check memory health`, `update memory confidence`.

## When not to use it

- You want to search or create memories: use [`memory`](memory.md).
- You want a narrative report across memory systems: use [`memory-documentary`](memory-documentary.md).

## Quick start

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:memory-enhancement`. The agent loads it when your request matches, and [`memory-search`](memory-search.md) chains results through it. To ask for it by name, say:

```text
Use the memory-enhancement skill to verify the citations in the testing/foo memory.
```

The skill runs the verifier and lists each citation as `[PASS]` or `[FAIL]` with a reason.

## What you get

Human-readable output for one memory:

```text
testing/demo:
  [PASS] src/api.py - File exists
  [FAIL] src/missing.py - File not found: src/missing.py
```

A memory id is its path under the memories directory without `.md`, so `.serena/memories/testing/foo.md` has the id `testing/foo`.

The `health` command reports `total_memories`, `total_citations`, `valid_citations`, `stale_citations`, `broken_citations`, `unverified_citations`, `health_score`, `stale_memories`, and `recommendations`. It does not detect orphans or rank staleness.

| Score range | Meaning | Action |
| --- | --- | --- |
| 0.9 to 1.0 | High confidence | Trust the memory. |
| 0.7 to 0.9 | Medium confidence | Review stale citations. |
| 0.5 to 0.7 | Low confidence | Update the memory or mark it obsolete. |
| 0.0 to 0.5 | Very low confidence | The memory is likely outdated. |

> [!WARNING]
> A memory with no citations scores high on validity. Read a high score as "nothing is known to be broken", not "this was checked against code". Check `total_citations` before you trust a score.

## Advanced use

There is no add-citation command. A citation is a text line in the memory body:

```text
[cite:file](src/api.py) - the error handler lives here
```

The syntax is `[cite:<source-type>](<target>) - <context>`. The `source-type` is one of `file`, `function`, `issue`, `pr`, `adr`, `memory`, or `url`. The target is a repository-relative path or identifier. Context is optional. The parser skips fenced code blocks and inline code. An unrecognized `source-type` warns on stderr and drops the citation, so verify after you edit. A `citations:` block in YAML frontmatter is not read.

Run the CLI from the root of a checkout of this repository. Global options go before the subcommand. After it, they exit 2.

```bash
uv run python -m memory_enhancement --repo-root . --memories-dir .serena/memories verify-all --json
```

| Command | Options | Exit 1 when |
| --- | --- | --- |
| `verify` | `--memory-id ID` | A citation is invalid, or the id is unknown. |
| `verify-all` | `--json` | Any citation is invalid. |
| `health` | `--json`, `--text`, `--markdown` (default; mutually exclusive) | Any citation is broken or stale, or any memory is stale. |
| `graph` | `--start ID` (required), `--depth N` | The start id is unknown. |
| `confidence` | none | Never (exit 0). |
| `search` | `QUERY`, `--top N`, `--json` | Never (exit 0). |

`--memories-dir` must resolve inside `--repo-root`, or the CLI exits 1. The `confidence` command prints `<memory-id>: <score>` for every memory. It computes scores on each run and does not write them back.

The score blends four factors, clamped to 0.0 through 1.0:

| Factor | Weight | Definition |
| --- | --- | --- |
| Citation validity | 0.50 | Valid citations divided by total citations. 1.0 when there are none. |
| Update recency | 0.25 | Decays linearly to 0 over 90 days since `updated_at`. |
| Link count | 0.15 | Outgoing links divided by 10, capped at 1.0. |
| Memory freshness | 0.10 | Decays linearly to 0 over 365 days since `created_at`. |

There is no exemption mechanism. `exempt: true` in frontmatter has no effect.

In this repository's CI, `memory-health.yml` posts a non-blocking health comment on PRs that touch memory files. `citation-verify.yml` runs `verify-all` and blocks the PR on a stale or broken citation.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`memory-search`](memory-search.md): chains its results through this skill.
- [`curating-memories`](curating-memories.md): updates citations when memories change.
- [`reflect`](reflect.md): captures citations from learnings that reference code.
- Source: [`SKILL.md`](../../src/claude/skills/memory-enhancement/SKILL.md)
- References: [`confidence-scoring.md`](../../src/claude/skills/memory-enhancement/references/confidence-scoring.md), [`examples.md`](../../src/claude/skills/memory-enhancement/references/examples.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
