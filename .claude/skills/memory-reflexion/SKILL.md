---
name: memory-reflexion
version: 0.2.0
description: Tier 2 episode extraction, the reflexion write path split out of the
  memory router per ADR-063. Extracts an episode from a completed session log so
  later sessions can replay what was tried and what it cost. Use when you say
  `extract episode from session`, `record what happened this session`, or
  `re-extract this episode`. Do NOT use for Tier 1 lookups (use memory-search)
  or for adding citations (use memory-enhancement).
license: MIT
metadata:
  adr: ADR-007, ADR-037, ADR-038, ADR-056, ADR-063, ADR-089
  type: operation
  parent: memory
---

# Memory Reflexion

Tier 2 episodic write operations: the reflexion write path extracted from the
`memory` router per ADR-063 (memory-skill decomposition). `memory` still routes
here; a caller that needs only to record a session outcome loads this sub-skill
instead of the full memory surface.

Reflexion is one operation: extract an episode from a completed session log.
The episode record is the durable artifact. It is committed to the repository
and read directly by downstream consumers.

> [!NOTE]
> This sub-skill previously carried a second step that folded episodes into a
> derived causal graph (Tier 3). ADR-089 removed that layer: nothing read it,
> and its aggregated output was noise. Episodes are unaffected and remain the
> system of record. See ADR-089 for the evidence.

## Triggers

Use this skill when the user says:

- `extract episode from session` to capture a completed session as an episode
- `record what happened this session` for the reflexion write path
- `re-extract this episode` to refresh a record over an existing episode file

## Quick Start

```bash
# Extract an episode from a completed session log (Tier 2)
python3 .claude/skills/memory/scripts/extract_session_episode.py "<session-log-path>"

# Re-extract over an existing episode, merging rather than clobbering
python3 .claude/skills/memory/scripts/extract_session_episode.py "<session-log-path>" --preserve
```

The script is canonical and shared with the `memory` router; this sub-skill does
not reimplement it. It lives at
`.claude/skills/memory/scripts/extract_session_episode.py`.

## Quick Reference

| Operation | Script | Key Parameters |
|-----------|--------|----------------|
| Extract episode (Tier 2) | `extract_session_episode.py` | `session_log_path`, `--output-path`, `--force`, `--preserve` |

`--force` and `--preserve` are mutually exclusive. `--force` overwrites an
existing episode file. `--preserve` merges a fresh extraction over the existing
record without dropping richer data already there.

## Who Reads Episodes

Nothing does, today. Outside this module, its own tests, and documentation
examples, no code calls `get_episodes`, `get_episode`, or
`get_decision_sequence`. Verify before you rely on the opposite:

```bash
git grep -n "get_episodes\|get_episode(\|get_decision_sequence" -- '*.py' \
  | grep -v "memory_core/\|/tests/\|test_"
```

An earlier version of this section claimed three consumers. That claim was
false and the ADR-089 review retracted it. One of the three excludes episode
paths from a churn signal, one allowlists the episode path prefix, and one
generates and stages episodes. None reads episode content.

Write for a reader that does not exist yet. Episodes are the primary record of
what happened in a session, and their value is that they can be queried later.
That does not make an incomplete record harmless, so the extraction rules below
still bind.

Tier 2 survived the ADR-089 removal on derivation distance and cost, not on
readership. Episodes are the primary record and are many small files. The
removed causal graph was derived from them and was a single rewritten blob.
Whether episodes earn their keep is an open question that ADR-089 explicitly
declined to settle.

## Schema

The episode schema is defined in ADR-038 and documented in detail in
[references/reflexion-memory.md](references/reflexion-memory.md). That reference
travels with this sub-skill: it covers the episode schema and the integration
workflow. Read it when you need the exact field shapes.

## Ordering

```text
Completed session?
│
└─► extract_session_episode.py "<session-log-path>"
    └─► Produces an episode record in the repository episode store (Tier 2)
```

Only extract from COMPLETED sessions. A partial session produces an incomplete
episode, and an incomplete episode is a falsified record of what happened. It
is committed, so it outlives the session that produced it.

## Graceful Degradation

The reflexion write path is local-only. Serena is the canonical store and
travels with the repository (ADR-007). Episode extraction reads a session log
and writes an episode record. It requires no network store, so there is no
fallback to invoke here.

## Verification

| Operation | Verification |
|-----------|--------------|
| Episode extracted | Episode record written; CLI reports the episode ID and outcome |
| Episode staged | The new episode file appears in `git status` |
| Re-extraction | `--preserve` leaves existing richer fields intact; `--force` replaces the record |

## Anti-Patterns

| Anti-Pattern | Do This Instead |
|--------------|-----------------|
| Extracting from an in-progress session | Only extract from COMPLETED sessions |
| Re-running without a write mode on an existing episode | Choose `--force` (replace) or `--preserve` (merge) deliberately |
| Hand-editing an episode record | Re-extract from the session log |

## Process

### Phase 1: Extract

Run `extract_session_episode.py` against a completed session log. Confirm the
CLI reports an episode ID and a recognized outcome.

### Phase 2: Verify

Confirm the episode file exists in the episode store and that its outcome
matches how the session actually ended. An episode that records
`success` for a session that was abandoned is worse than no episode, because it
is committed and a later reader has no way to tell it from a true one.

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
| Episode file already exists | A prior extraction wrote it | Choose `--force` to replace or `--preserve` to merge |
| Outcome reads wrong | Session log terminal state is ambiguous | Fix the session log first; the episode derives from it |

See [references/reflexion-memory.md](references/reflexion-memory.md) for the full
troubleshooting table and the retrospective integration workflow.

## Extension Points

| Extension | How to Add |
|-----------|------------|
| New episode field | Extend the ADR-038 episode schema; update `extract_session_episode.py` and the reference |
| Downstream consumer | Read episode records directly; chain through `memory-search` for retrieval |

Before adding a derived aggregation over episodes, read ADR-089. The last one
was deleted for having no reader and producing noise. A new one needs a named
consumer that is not itself memory tooling.

## References

- ADR-007: Memory-first architecture (canonical store, local-only posture)
- ADR-037: Memory router architecture (the router this sub-skill delegates from)
- ADR-038: Reflexion memory schema (episode shape)
- ADR-056: Skill output format standardization (the envelope this sub-skill emits)
- ADR-063: Memory skill decomposition (this extraction)
- ADR-089: Removal of the derived causal-memory tier
- [references/reflexion-memory.md](references/reflexion-memory.md): full schema and integration workflow
