---
type: design
id: DESIGN-028
title: Disposition-driven Serena consolidation after the extraction streams
status: draft
priority: P3
related:
  - REQ-030
  - TASK-039
created: 2026-09-22
updated: 2026-09-22
author: spec
tags:
  - governance
  - memory
  - knowledge-persistence
  - cleanup
---

# DESIGN-028: Disposition-driven Serena consolidation after the extraction streams

## Requirements Addressed

REQ-030 acceptance criteria AC-1 through AC-10, per
`.project-toolkit/specs/requirements/REQ-030-serena-post-migration-cleanup.md`.

## Measured starting state

Taken on branch `feat/5394-serena-cleanup` at merge base `f562b5df2`.

| Measure | Value | Source |
|---|---:|---|
| Memory markdown files | 1037 | `rglob('*.md')`, `.obsidian` excluded |
| Total bytes | 3077516 | `stat().st_size` sum |
| Estimated tokens | 752655 | `count_memory_tokens.py`, tiktoken `cl100k_base` |
| Top-level files | 131 | direct children of `.serena/memories` |
| Top-level indexes | 44 | `*-index.md` |
| Broken index links | 0 | every `](path.md)` target resolves |
| Placement: normative | 181 | `check_memory_placement.py --json` |
| Placement: suspect | 187 | same run |
| `list_memories` payload | 11629 tokens | live MCP call on this checkout |

## The false premise in the navigation layer

At merge base `f562b5df2`, `.serena/memories/README.md` said subdirectory
memories were hidden from `list_memories`, and
`.serena/memories/memory/serena-memory-subdirectory-convention.md` repeated it
and recorded a saving of about 4,700 tokens per session, measured on
2026-02-14.

A live `list_memories` call on this checkout returned every name in the tree,
top level and nested, at 11,629 tokens. Top-level names alone would be 1,232.
The claim was false against the current runtime, so the index layer buys no
listing saving today. It still routes keywords, which is why this design keeps
it and corrects the claim instead of deleting the layer. `README.md` now states
the observed behavior.

Correcting the claim is in scope because both files are required reading for
this issue and the index policy rests on them. Re-architecting the tree is not:
moving the 87 top-level non-index memories is recorded as a finding.

## Design

### Step 1: disposition table

Six families, 63 files: `agent-behavior/` (4), `agent-workflow/` (11),
`autonomous/` (6), `orchestration/` (14), `session/` (17), `protocol/` (11).

Each file gets one verb.

| Verb | Condition | Result |
|---|---|---|
| delete | The named owner fully represents it, or it describes a retired mechanism, and no dated incident, measurement, or quantitative finding remains | File removed, index rows removed |
| thin | Evidence survives, normative or procedural text duplicates the named owner | Policy text removed, evidence kept, pointer added |
| keep | Already evidence-only | No change |

A `delete` or a `thin` without a real owner path plus a line number or a quoted
heading is rejected and downgraded to `keep`. The table lands at
`.project-toolkit/analysis/5394-serena-cleanup-disposition.md`.

### Step 2: apply

Deletes first, then thins. A thinned file keeps its `<!-- placement: evidence -->`
marker when it already carries one, so `check_memory_placement.py` stays quiet.

### Step 3: index sweep

For each of the 44 top-level indexes:

1. Remove each row whose target this change deleted.
2. Remove the index when it has no rows left, when every row pointed at a
   deleted file, or when it only proxies a first-class rule, skill, or agent
   surface and routes to no surviving evidence (REQ-030 step 3).
3. Leave an index that still routes to surviving memories.

The proxy condition is evaluated per index and none met it: every top-level
index still routes to at least one memory that holds evidence a first-class
artifact does not carry. Removing an index whose targets survive would make
those files unreachable from `memory-index.md` and would raise the orphan
count, so this design never does it.

### Step 4: `memory-index.md`

1. Drop each route to a deleted file.
2. Retire the `[User Constraints (MUST READ)]` section framing. The section
   presents policy as a Serena capability. One row already points at
   `.claude/rules/universal.md` as canonical; the other becomes a plain
   evidence route under an existing section.
3. Drop the row for any index this change removed.

### Step 5: README correction

Replace the "hidden from `list_memories`" claim with the measured behavior and
state what the index layer is for now: keyword routing, not listing reduction.

### Step 6: repository sweep

For each deleted path, search every tracked file, with no extension filter, and
update only the references that this change makes semantically stale. A
citation inside a session log, a retrospective, or an archive that records
history stays; a link in a live document is repointed.

## Risk register (pre-mortem)

| Risk | Likelihood | Mitigation |
|---|---|---|
| A delete removes the only record of an incident | Medium | AC-3 forbids it; every delete row names the owner, and the reviewer checks the row against the file in the diff |
| Removing an index orphans surviving memories | Medium | Step 3 removes an index only when it has no surviving rows |
| The orphan ratchet rises | Low | Deletion only lowers the file count; the run is checked before the PR |
| Token counts go stale in `memory-index.md` | Medium | `update_memory_index_tokens.py` runs, then `--check` |
| Scope drifts into the other 368 flagged files | Medium | REQ-030 "Out of scope" names them; the disposition table covers six families only |
| A deleted path breaks a script or a workflow | Low | Step 6 searches every tracked file for each deleted path, with no extension filter |

## Deferred

The four extraction candidates from the #5393 inventory, and the relocation of
the 87 top-level non-index memories. Both are recorded in the disposition file
under "Findings handed on", not acted on here.
