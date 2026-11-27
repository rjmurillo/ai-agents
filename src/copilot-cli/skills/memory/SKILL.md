---
name: memory
version: 0.4.0
description: "Thin router for the tiered memory system; picks the focused sub-skill. Use when you ask \"remember this\", \"retain a decision\", \"what do we know about X\", or \"recall prior context\" and are unsure which operation you need. Do NOT use for citations (use memory-enhancement) or cross-system reports (use memory-documentary)."
license: Apache-2.0
metadata:
  capability:
    kind: orchestrator
    owns:
      - memory-operation-routing
    status: active
  adr: ADR-038, ADR-063, ADR-106
  timelessness: 8/10
  routing:
    role: conditional-adjunct
    invoker: research
    trigger: research redirects a search of this repository here
    user-facing: true
---
# Memory System Skill

Thin router across the tiered memory system. Each operation lives in a focused
sub-skill (ADR-063 memory-skill decomposition); this router points you at the
right one so a caller loads only the surface it needs.

---

## When to Use This Skill

| Scenario | Use Memory Router? | Alternative |
|----------|-------------------|-------------|
| Not sure which memory operation you need | Yes | - |
| Retain a durable project fact | Yes | Write procedure below |
| Tier 1 search only | If `memory-search` is unavailable | `memory-search` sub-skill |
| Record a completed session | No | `memory-reflexion` sub-skill |
| Pre-change memory-first gate | If `memory-gate` is unavailable | `memory-gate` sub-skill |
| Health, token count, benchmark | No | `memory-maintenance` sub-skill |
| Periodic durable/dated consolidation, index tidy | No | `memory-consolidate` sub-skill |
| Agent needs deep multi-source context | No | `context-gather` skill |
| Human at CLI | No | `/memory-search` command |

See the [context-gather skill](../context-gather/SKILL.md) for the
multi-source pre-work gather and its
[references/context-retrieval.md](../context-gather/references/context-retrieval.md)
for the source-priority strategy (the former
context-retrieval agent folded into that reference, which moved here from the
retired knowledge-graph skill).

---

## Related Sub-Skills

Use this skill to retain durable project facts. For other operations, load the
focused sub-skill when available.

| Sub-Skill | Operation | Load When |
|-----------|-----------|-----------|
| `memory-search` | Scoped project memory search | You need facts, patterns, or rules |
| `memory-reflexion` | Tier 2 episode extraction | You are recording a completed session |
| `memory-gate` | Memory-First Gate (BLOCKING) and Chesterton's Fence protocol | You are about to change an existing system |
| `memory-maintenance` | Health check, token count, size validation, benchmark, density | You are maintaining the memory stores |
| `memory-consolidate` | Periodic consolidation of the indexed Serena corpus | You are doing a periodic memory cleanup pass |

---

## Triggers

Use this skill when the user says:

- `remember this` for durable fact retention
- `check memory tier health` for system status (routes to memory-maintenance)
- `extract episode from session` for session replay (routes to memory-reflexion)
- `memory-first gate` before changing an existing system (routes to memory-gate)
- `consolidate memory` for a periodic durable/dated review and index tidy (routes to memory-consolidate)

---

## Decision Tree

```text
What do you need?
│
├─► Current facts, patterns, or rules?
│   └─► memory-search, or the recall procedure below
│
├─► About to change existing code, a constraint, or a protocol?
│   └─► memory-gate, or the recall procedure below before changing anything
│
├─► Record what happened in a completed session?
│   └─► memory-reflexion sub-skill (Tier 2 episode extraction)
│
├─► A measured result contradicts a memory, ADR, skill, or common guidance?
│   └─► memory-gate contradiction log (decision-<slug>), or the write procedure below if memory-gate is unavailable
│
├─► Store new factual knowledge directly?
│   └─► Follow the project memory write procedure below
│
├─► Check health, count tokens, benchmark, or improve graph density?
│   └─► memory-maintenance sub-skill
│
├─► Periodic pass: separate durable from dated, merge overlaps, tidy the index?
│   └─► memory-consolidate sub-skill
│
└─► Not sure which tier?
    └─► Start with recall, then check episodes if needed
```

For deeper guidance on picking a tier, see
[references/tier-selection-guide.md](references/tier-selection-guide.md).

---

## Write a Durable Project Fact

1. Keep a verified decision, result, or reusable lesson. Record what happened,
   the reason, the date, and the evidence. Put required behavior in rules or
   instructions. Keep secrets, private data, and transcripts out of notes.
   For a measured contradiction, name the entry `decision-<slug>` and record
   five fields: the question, the conventional answer with its citation, the
   first-principles position, the evidence, and the decision with where it
   lives in the code. Write it to the repository store in step 4 first; a
   memory service may hold a copy, never the only one.
2. Use the destination authorized by the user or repository. If neither names
   one, use an available write capability only when its permission and project
   scope are clear. Use the capability's actual tool schema. A global account
   or an unknown bank does not establish project scope. Before you write
   through a memory service, confirm it is bound to the current checkout. If
   you cannot confirm it, do not write through it; report the gap.
3. Search the destination for the same fact before writing. Update a matching
   entry when supported. Save one self-contained note and verify it landed.
   If the result of a write is ambiguous, check that destination before retrying.
4. If no writable project tool is available or the chosen store is local, use the established repository
   memory directory. If the repository has none, use
   `.project-toolkit/memory/notes/<topic>/<descriptive-name>.md` from its root.
   Check for an existing note first. Create the directory only when saving.
   Confirm the destination resolves inside the current checkout before writing.
   Follow the repository's policy for version control.
5. State what you saved and where. When storage is unavailable, report the
   gap. Delete or rename records only when the user asks.

### Serena in Repositories That Already Use It

Use the repository's established corpus. If the Serena tool is available,
use its project binding and read relevant entries by name. If it is absent,
use file tools on the same corpus.

### Serena memory writes: check the checkout first

Serena writes to the checkout active at server start (`--project` root),
not your cwd. Call `mcp__serena__write_memory`, `edit_memory`,
`delete_memory`, or `rename_memory` only from that checkout. A linked worktree
(`git rev-parse --git-dir` differs from `--git-common-dir`) never qualifies.
In one, unsure, or without a shell, do not call them: edit the repository memory
files in your own checkout, or return the change to the parent session. Delete or
rename only when asked. New memory: `<topic>/<name>` plus a `memory-index.md` line.

See `universal.md` MUST NOT 11.

---

## Progressive Disclosure

List names, read matching details, and follow relevant cross-references. This prevents loading a large memory when a small slice
answers the query (up to an 87% token reduction). The `memory-search` sub-skill
owns the Tier 1 index-then-read flow; start there.

Use descriptive filenames for repository notes. In an indexed Serena corpus,
update the domain `*-index` when adding a note.

---

## Serena Write Conventions

These conventions govern writing a new Serena memory and registering it in its
domain index. They are the load-bearing rules absorbed from the former `memory`
agent. For in-file obsolete-marking, use the `curating-memories`
skill. For cross-file deduplication, use the `memory-consolidate` skill. For
cross-linking, use the `memory-maintenance` skill.

### Naming

- Memory name: `<topic>/<descriptive-name>`, lowercase with hyphens, under an
  existing topic folder when one fits (for example `pr-review/security`).
- Entity ID inside the file: `{domain}-{description}`, kebab-case, no prefix
  (for example `pr-enum-001`). File name and entity ID are separate; do not
  conflate them.

### Index-Table Insertion (hazard)

Domain index files (`skills-*-index.md`) contain ONLY a two-column table. When
you add a memory you MUST insert AFTER the last existing DATA row, never after
the header or the delimiter:

```text
| Keywords | File |    <-- header row
|----------|------|    <-- delimiter row (SKIP THIS)
| existing | file |    <-- data rows; insert after the LAST one
```

Inserting after the header or delimiter corrupts the table and breaks name-based
discovery for every reader. Do not add titles, statistics, or prose to an index
file.

### Relations (encoded in the memory body)

```markdown
## Relations

- **supersedes**: [previous-file-name]
- **depends_on**: [dependency-file-name]
- **related_to**: [related-file-name]
```

`supersedes` (new version replaces old), `depends_on` (requires another memory),
`related_to` (loose association).

### Source Tracking (required on every observation)

```text
[YYYY-MM-DD] [Source]: [Observation content]
```

Source forms: `[agent-name]`, `[doc:path]`, `[decision:ADR-NNN]`, `[user]`,
`[ext:source]`. Reasoning over actions: record WHY a choice was made, not just
WHAT was done.

### Conflict Resolution

When observations contradict, prefer the most recent, create a new memory with a
`supersedes` relation, and prefix with `[REVIEW]` when accuracy is uncertain.

---

## Storage Locations

| Data | Location |
|------|----------|
| Durable project facts | Authorized project store or repository Markdown |
| Episodes | Local episode store (see `memory-reflexion`) |

---

## Anti-Patterns

| Anti-Pattern | Do This Instead |
|--------------|-----------------|
| Skipping the memory-first gate | Route to `memory-gate` before changing existing systems |
| Loading the full router for one operation | Load the focused sub-skill instead |
| Tier confusion | Follow the decision tree; start at Tier 1 |
| Consolidating atomic memories | Keep one concept per file; update the index on add |

---

## See Also

Router-owned references, shared across the memory sub-skills. Operation-specific
references travel with their sub-skill (ADR-063).

| Document | Content |
|----------|---------|
| [tier-selection-guide.md](references/tier-selection-guide.md) | When to use each tier |
| [zettelkasten-memory-agents.md](references/zettelkasten-memory-agents.md) | Atomic memory principle and auto-linking |
| [codebase-knowledge-graph.md](references/codebase-knowledge-graph.md) | GitNexus pattern for structural context via MCP |

---

## Verification

| Operation | Verification |
|-----------|--------------|
| Routed to sub-skill | Sub-skill SKILL.md loaded and its verification gate applied |
| Search completed | Result count > 0 OR logged "no results" |
| Fact retained | The saved entry exists in the selected project store |
| Episode extracted | JSON file in `.project-toolkit/memory/episodes/` |
| Health check | All tiers show "available: true" |

Verification checklist:

- [ ] The selected operation and destination match the request
- [ ] The result has a source or a verified write destination

---

## Process

### Phase 1: Route

Match the request to an operation using the decision tree.

### Phase 2: Delegate

Use the write procedure above to retain facts. Follow the selected sub-skill's
procedure when available.

### Recall without a sub-skill

Query an available recall capability when its project scope is clear.
Search the established repository corpus or notes if that query has no
relevant results, or if scoped recall is unavailable.
Run the bundled `search_memory.py` or use file tools. Before changing
an existing system, check Git history for missing rationale. Verify claims
against current sources and record the sources and coverage gaps.

### Phase 3: Report

Return structured results to the caller with source attribution.

---

## Scripts

The router owns the canonical memory scripts. Sub-skills delegate to these paths
(ADR-063); the router does not duplicate them.

| Script | Purpose | Exit Codes |
|--------|---------|------------|
| `search_memory.py` | Search repository Markdown and episodes | 0=success, 1=error |
| `count_memory_tokens.py` | Token counting with tiktoken caching; lists the 200 largest files, `--limit 0` lists all | 0=success, 1=error |
| `test_memory_size.py` | Memory atomicity validation | 0=pass, 1=violations |
| `test_memory_health.py` | System health dashboard | 0=success |
| `extract_session_episode.py` | Episode extraction; `--validate` checks the store at rest, `--fix` repairs backwards commit order; `--dry-run` extracts without writing | 0=success, 1=error, 2=violation or bad flag |
| `repair_episode_causal_links.py` | Restore causal edges in flattened episodes; `--check` or `--dry-run` reports without writing | 0=success, 1=an episode is invalid, 2=episodes dir missing |
| `migrate_causal_version.py` | One-shot migration: stamps `causal_order_version=2` on legacy episodes; `--dry-run` previews counts without writing | 0=all stamped, 1=some skipped, 2=bad path |
| `measure_memory_performance.py` | Serena search benchmark, by phase | 0=success, 1=error |
| `improve_memory_graph_density.py` | Graph density improvement | 0=success, 1=error |
| `convert_index_table_links.py` | Index table link conversion; `--dry-run` previews | 0=success, 1=error |
| `convert_memory_references.py` | Convert backtick memory references to Markdown links; `--dry-run` previews | 0=success, 1=error |
| `invoke_memory_cross_reference.py` | Cross-reference memories | 0=success, 1=error |

Invoke it through the plugin-root locator:

```bash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/memory/scripts/test_memory_health.py --format table; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

---

## Related Skills

| Skill | When to Use Instead |
|-------|---------------------|
| `memory-search` | Tier 1 search only; smaller context than the router (ADR-063) |
| `memory-reflexion` | Tier 2 episode extraction (ADR-063) |
| `memory-gate` | Memory-First Gate and Chesterton's Fence protocol (ADR-063) |
| `memory-maintenance` | Health, token count, size, benchmark, density (ADR-063) |
| `memory-consolidate` | Periodic durable/dated consolidation, overlap merge, index tidy |
| `memory-enhancement` | Add citations, verify code references, track confidence |
| `memory-documentary` | Narrative cross-system memory reports |
| `curating-memories` | In-file obsolete-marking (supersession markers) |

<!-- vendor-portability: .project-toolkit/memory/notes and .project-toolkit/memory/episodes belong to the consumer repository. The skills create each directory when saving there. -->
