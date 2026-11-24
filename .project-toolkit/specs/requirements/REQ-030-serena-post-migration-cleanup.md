---
type: requirement
id: REQ-030
title: Consolidate Serena memories after the rules, skills, and agents extraction
status: draft
priority: P3
category: functional
source: GH-5394
epic: EPIC-5456
related:
  - REQ-028
  - REQ-029
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

# REQ-030: Consolidate Serena memories after the rules, skills, and agents extraction

## Step 0 First Principles

### Q1 Demand Reality

1. Issue #5394's author, `rjmurillo`, opened the issue and added the
   reconciliation comment that fixes its ownership boundary.
2. Epic #5456 sequences #5394 as the terminal Phase 3 pass behind #5391,
   #5392, and #5393. All three are now closed and merged to `main`.
3. The #5393 inventory hands three named stale files and 28 family-level
   thinning recommendations to this issue by name.

### Q2 Status Quo

`.serena/memories` holds 1,037 markdown files, 3,077,516 bytes, and 752,655
tiktoken `cl100k_base` tokens. Forty-four top-level index files carry a second
navigation layer above the topic subdirectories. `README.md` states that
subdirectory memories are "hidden from `list_memories`", which is the stated
reason the index layer exists. A live `list_memories` call on this checkout
returned every name in the tree, 11,629 tokens, so the premise is false and the
index layer buys no listing saving.

`memory-index.md` carries a `[User Constraints (MUST READ)]` section that
presents policy as a Serena capability, though `.claude/rules/universal.md` now
owns that content.

### Q3 Desperate Specificity

`orchestration/orchestration-validation-gate.md` requires a Session End
checklist. `.claude/rules/session-logs.md:9` states "Session log creation is
discontinued". An agent that retrieves the memory runs a checklist against an
artifact class the repository retired, and the memory outranks nothing, so the
agent loses the time and produces no output the reviewer can use.

### Q4 Narrowest Wedge

One PR, about 4 hours AI-assisted (human team: about 3 days):

1. Decide one disposition for every file in the six families this issue names,
   citing the first-class owner for each delete and each thin.
2. Apply the deletes and the thins.
3. Sweep the 44 top-level indexes: remove an index whose targets are gone or
   that proxies a first-class surface, shrink the rest.
4. Correct `README.md` and `memory-index.md`.
5. Sweep the repository for references to deleted paths.

### Q5 Observation

Deterministic, already in the repository:

- `scripts/validation/memory_index.py --ci --orphan-policy ratchet`: index rows
  resolve, orphan report, keyword coverage.
- `scripts/validation/check_memory_placement.py --path .serena/memories --json`:
  normative-versus-evidence classification per file.
- `scripts/update_memory_index_tokens.py --check`: token counts per index row.
- `scripts/validate_memory_tier.py`, the `memory-size` hook job.
- `.claude/skills/memory/scripts/count_memory_tokens.py`: token totals.

### Q6 Future-fit

Placement is settled by REQ-028. This issue decides no new taxonomy, adds no
validator, and creates no measurement authority; #5400 owns measurement, #5396
owns capability metadata, #5397 owns structural ratchets, and #4313, #4776,
#4705 own index-validator defects.

## Problem statement

After #5392 and #5393 moved normative behavior out of Serena, the memory tree
still carries duplicate authority, stale navigation, and a README that
documents an architecture the runtime does not provide. A reader cannot tell
which copy of a behavior binds.

## User stories

1. As an agent resolving a procedure, I want one authoritative artifact per
   concept, so that I do not follow a stale Serena copy.
2. As a maintainer reading `.serena/memories/README.md`, I want the navigation
   contract to match observed `list_memories` behavior, so that I do not build
   on a false premise.
3. As a reviewer, I want a checked-in disposition table naming the owner for
   every deleted and thinned file, so that I can check each decision.

## Ontology

- **Thin**: remove the normative or procedural text, keep the observation,
  measurement, incident, or rationale, and add a pointer to the owner.
- **Family**: one topic subdirectory under `.serena/memories/`.
- **Index layer**: the 44 top-level `*-index.md` files.

## Acceptance Criteria

**AC-1**: Every file in `agent-behavior/`, `agent-workflow/`, `autonomous/`,
`orchestration/`, `session/`, and `protocol/` carries one recorded disposition
of `delete`, `thin`, or `keep` in `.project-toolkit/analysis/5394-serena-cleanup-disposition.md`.

**AC-2**: Every `delete` row and every `thin` row names the first-class owner
as a real path with a line number or a quoted heading.

**AC-3**: No file that holds a dated incident, a measurement, or a quantitative
finding is deleted.

**AC-4**: `memory-index.md` contains no route to a deleted file, and no section
that presents a rule, skill, or agent capability as a Serena capability.

**AC-5**: Every surviving top-level index resolves all of its rows to existing
files. An index removed by this change leaves no memory unreachable from
`memory-index.md`.

**AC-6**: `.serena/memories/README.md` states the observed `list_memories`
behavior and no longer claims that subdirectory memories are hidden from it.

**AC-7**: `memory_index.py --ci --orphan-policy ratchet` passes, the orphan
count does not rise, `update_memory_index_tokens.py --check` passes, and
`check_memory_placement.py --ci` passes.

**AC-8**: A repository-wide search for each deleted path returns no consumer
that this change leaves broken.

**AC-9**: The PR body carries the before and after table (files, bytes, tokens,
top-level indexes, broken links) and the disposition count table.

**AC-10**: The memory tree is smaller in files, bytes, and tokens than the
merge base, or the disposition table records why a family was preserved.

## Rationale

The placement contract already states that a rule, skill, or agent outranks a
memory on overlap. This change applies that rule to files whose owner landed in
#5392 and #5393 and stops there. It optimizes for removing duplicate authority,
not for a deletion count.

## Dependencies

- #5391 placement contract (`.claude/rules/knowledge-persistence.md`): closed.
- #5392 rules extraction: closed, PRs #5847 and #5849.
- #5393 skills and agents extraction: closed, PR #5874, inventory at
  `.project-toolkit/analysis/5393-serena-workflow-inventory.md`.
- #5400 measurement mechanism: open, so this PR uses existing deterministic
  tooling for its evidence and adds no permanent measurement authority.

## Out of scope

- Thinning the placement-flagged memories outside the six named families. The
  full-tree scan reports 181 normative and 187 suspect files; a per-file pass
  over all of them spans sessions and is an ocean, not a lake.
- Any change to `memory_index.py`, `check_memory_placement.py`, or their gates.
  #4313, #4776, and #4705 own those defects.
- Capability or dependency metadata (#5396).
- Structural-duplication ratchets (#5397).
- A context-growth ratchet or a second token-budget authority (#5400).
- Relocating the 87 top-level non-index memories into topic subdirectories.

## Deferred

The four extraction candidates the #5393 inventory names (`bash-integration`
exit contract, `coderabbit` configuration reference, `design` authoring norms,
`gemini` configuration reference) each need a buy-versus-reuse check and a new
owner. None is created here; the disposition table records them as deferred.

## Open questions

None. The reconciliation comment settles the ownership boundary and the
measurement rule.

## CVA summary

Common across the six families: a memory that duplicates a first-class owner.
Variable: whether evidence survives the removal. The disposition verb captures
the variation, so no new abstraction is needed.

## Buy-vs-build decision

Reuse. Every check this change runs already exists in `scripts/validation/`.

## Complexity classification

Complicated. The rules are known and the procedure is repeatable; the cost is
per-file reading, not design.
