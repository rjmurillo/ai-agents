---
name: memory-reflexion
version: 0.1.0
description: Tier 2 episode extraction and Tier 3 causal-graph update, the
  reflexion write path split out of the memory router per ADR-063. Extracts an
  episode from a completed session log, then folds it into the causal graph so
  decision patterns accrue. Use when you say `extract episode from session`,
  `update causal graph`, or `record what happened this session`. Do NOT use for
  Tier 1 lookups (use memory-search) or for adding citations (use
  memory-enhancement).
license: MIT
model: claude-sonnet-4-6
metadata:
  adr: ADR-007, ADR-037, ADR-038, ADR-056, ADR-063
  type: operation
  parent: memory
---

# Memory Reflexion

Tier 2 episodic and Tier 3 causal write operations: the reflexion write path
extracted from the `memory` router per ADR-063 (memory-skill decomposition).
`memory` still routes here; a caller that needs only to record a session outcome
loads this sub-skill instead of the full memory surface.

Reflexion is one operation with two ordered steps. First extract an episode from
a completed session log (Tier 2). Then update the causal graph from that episode
(Tier 3) so success and failure patterns accrue across sessions. The two scripts
share the ADR-038 schema, so they travel together as a single sub-skill rather
than two shallow pass-throughs.

## Triggers

Use this skill when the user says:

- `extract episode from session` to capture a completed session as an episode
- `update causal graph` to fold episodes into decision patterns
- `record what happened this session` for the full reflexion write path

## Quick Start

```bash
# Step 1: Extract an episode from a completed session log (Tier 2)
python3 .claude/skills/memory/scripts/extract_session_episode.py "<session-log-path>"

# Step 2: Update the causal graph from extracted episodes (Tier 3)
python3 .claude/skills/memory/scripts/update_causal_graph.py

# Preview causal changes without writing
python3 .claude/skills/memory/scripts/update_causal_graph.py --dry-run
```

Both scripts are canonical and shared with the `memory` router; this sub-skill
does not reimplement them. They live at
`.claude/skills/memory/scripts/extract_session_episode.py` and
`.claude/skills/memory/scripts/update_causal_graph.py`.

## Quick Reference

| Operation | Script | Key Parameters |
|-----------|--------|----------------|
| Extract episode (Tier 2) | `extract_session_episode.py` | `session_log_path`, `--output-path` |
| Update causal graph (Tier 3) | `update_causal_graph.py` | `--episode-path`, `--dry-run` |

## Schema

The episode (Tier 2) and causal-graph (Tier 3) schemas are defined in ADR-038
and documented in detail in [references/reflexion-memory.md](references/reflexion-memory.md).
That reference travels with this sub-skill: it covers the episode schema, the
causal-graph schema, the query functions, and the integration workflow. Read it
when you need the exact field shapes or the pattern-extraction rules.

## Ordering

Reflexion is extract-then-update:

```text
Completed session?
│
├─► Step 1: extract_session_episode.py "<session-log-path>"
│   └─► Produces an episode record (Tier 2)
│
└─► Step 2: update_causal_graph.py
    └─► Folds episodes into nodes, edges, and patterns (Tier 3)
```

Only extract from COMPLETED sessions. A partial session produces an incomplete
episode that pollutes the causal graph. Run `update_causal_graph.py` after each
batch of extractions so the graph does not drift stale.

## Graceful Degradation

The reflexion write path is local-only and does not depend on Forgetful. Serena
is the canonical store and travels with the repository (ADR-007). Episode
extraction reads a session log and writes an episode record; causal-graph update
reads episodes and writes the graph. Neither step requires a network store, so
there is no Forgetful fallback to invoke here.

## Verification

| Operation | Verification |
|-----------|--------------|
| Episode extracted | Episode record written; CLI reports the episode ID and outcome |
| Graph updated | Stats show nodes, edges, or patterns added (or zero on a clean re-run) |
| Dry run | `--dry-run` prints the diff and writes nothing |

## Anti-Patterns

| Anti-Pattern | Do This Instead |
|--------------|-----------------|
| Extracting from an in-progress session | Only extract from COMPLETED sessions |
| Skipping the causal update | Run `update_causal_graph.py` after extractions |
| Letting the graph go stale | Re-run the update after each extraction batch |
| Hand-editing the causal graph | Re-extract and re-update; never edit the graph by hand |

## Process

### Phase 1: Extract

Run `extract_session_episode.py` against a completed session log. Confirm the CLI
reports an episode ID and a recognized outcome.

### Phase 2: Update

Run `update_causal_graph.py` to fold the new episode into the graph. Use
`--dry-run` first when you want to preview the node, edge, and pattern changes.

### Phase 3: Verify

Confirm the update stats show the expected nodes, edges, or patterns. A clean
re-run that adds zero is a valid outcome; the graph is already current.

## Related Skills

| Skill | When to Use Instead |
|-------|---------------------|
| `memory` | Router for search, health, or maintenance operations |
| `memory-search` | Tier 1 semantic lookup; smaller context than the full router |
| `memory-enhancement` | Add citations, verify code references, track confidence |
| `curating-memories` | Memory maintenance (obsolete, deduplicate, link) |

## Troubleshooting

| Symptom | Cause | Recovery |
|---------|-------|----------|
| Episode not found | Session log path wrong or session incomplete | Verify the session log path; confirm the session reached a terminal outcome |
| Causal graph not updating | No new episodes since last run | Extract a new episode first; a no-op update is valid |
| Path not found in graph | The decision sequence has no recorded edge | Extract more episodes covering that decision path |
| Pattern extraction issues | Too few episodes for a pattern threshold | Accumulate more episodes; patterns need repeated occurrences |

See [references/reflexion-memory.md](references/reflexion-memory.md) for the full
troubleshooting table, the query functions, and the retrospective integration
workflow.

## Extension Points

| Extension | How to Add |
|-----------|------------|
| New episode field | Extend the ADR-038 episode schema; update `extract_session_episode.py` and the reference |
| New pattern rule | Extend the causal-graph pattern logic in `update_causal_graph.py` |
| Downstream consumer | Read episodes or the causal graph; chain through `memory-search` for retrieval |

## References

- ADR-007: Memory-first architecture (canonical store, local-only posture)
- ADR-037: Memory router architecture (the router this sub-skill delegates from)
- ADR-038: Reflexion memory schema (episode and causal-graph shapes)
- ADR-056: Skill output format standardization (the envelope this sub-skill emits)
- ADR-063: Memory skill decomposition (this extraction)
- [references/reflexion-memory.md](references/reflexion-memory.md): full schema, query functions, and integration workflow
