---
type: task
id: TASK-039
title: Consolidate Serena memories after the rules, skills, and agents extraction
status: draft
priority: P3
related:
  - REQ-030
  - DESIGN-028
created: 2026-09-22
updated: 2026-09-22
author: spec
tags:
  - governance
  - memory
  - knowledge-persistence
  - cleanup
---

# TASK-039: Consolidate Serena memories after the rules, skills, and agents extraction

## Objective

Apply the placement contract to the six memory families that #5392 and #5393
left with duplicate authority, correct the navigation layer, and record the
evidence. Closes #5394.

## Milestone 1: disposition table (S)

1. Read every file in `agent-behavior/`, `agent-workflow/`, `autonomous/`,
   `orchestration/`, `session/`, and `protocol/`.
2. Record one verb per file with the owner path and line number.
3. Write `.agents/analysis/5394-serena-cleanup-disposition.md`.

Exit: 63 rows, every `delete` and `thin` row carries an owner citation.

## Milestone 2: apply the dispositions (S)

1. Delete the files marked `delete`.
2. Thin the files marked `thin`, keeping evidence and the placement marker.
3. Grep the repository for each deleted basename and update stale references.

Exit: `check_memory_placement.py --path .serena/memories --ci` passes.

## Milestone 3: navigation layer (S)

1. Remove index rows pointing at deleted files.
2. Remove an index that has no surviving rows.
3. Update `memory-index.md`: drop dead routes, retire the
   `[User Constraints (MUST READ)]` framing.
4. Correct the `list_memories` claim in `.serena/memories/README.md` and in
   `memory/serena-memory-subdirectory-convention.md`.
5. Run `uv run --frozen python scripts/update_memory_index_tokens.py`.

Exit: `memory_index.py --ci --orphan-policy ratchet` passes, orphan count does
not rise, `update_memory_index_tokens.py --check` passes.

## Milestone 4: evidence (S)

1. Recompute files, bytes, tokens, top-level indexes, broken links.
2. Put the before and after table and the disposition count table in the PR body.

Exit: PR body carries both tables.

## Dependency graph

```text
M1 -> M2 -> M3 -> M4
```

## Done definition

- Every REQ-030 acceptance criterion holds.
- Pre-PR validation passes.
- The PR references `Closes #5394`.
