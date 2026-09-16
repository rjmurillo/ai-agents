---
type: requirement
id: REQ-028
title: Authoritative placement contract for rules, skills, agents, and memories
status: draft
priority: P1
category: functional
source: GH-5391
epic: EPIC-5456
related:
  - DESIGN-026
created: 2026-09-16
updated: 2026-09-16
author: spec
tags:
  - governance
  - memory
  - knowledge-persistence
---

# REQ-028: Authoritative placement contract for rules, skills, agents, and memories

## Step 0 First Principles

### Q1 Demand Reality

Four named requesters, each with a written ask in this repository:

1. Issue #5391's author, `rjmurillo`, opened the issue asking for an
   authoritative placement taxonomy for rules, skills, agents, and Serena
   memories, and its reconciliation comment scopes the fix to the taxonomy
   plus a narrow placement validator.
2. Issue #5392 (rule extraction), blocked on #5391 landing first.
3. Issue #5393, blocked on #5391 landing first.
4. Issue #5394, blocked on #5392 and #5393, which are themselves blocked on
   #5391.
5. Epic #5456's own text: "Land #5391, then #5392 and #5393, to release
   #5394." The epic names #5391 as the unblocking step for three sibling
   issues, not a hypothetical future need.

### Q2 Status Quo

Today an agent choosing where to write a durable fact does this:

1. Reads `templates/rules/universal.md`'s "Choosing a persistence surface"
   section, which names three tiers: ephemeral (session log only),
   retrieval aid non-binding (Serena memory or Copilot Memory), and durable
   convention binding every contributor and harness (a rule file under
   `.claude/rules/<name>.md`).
2. Reads `templates/rules/knowledge-persistence.md`'s "Net-new information
   decision checklist," which repeats the same three destinations: rule,
   Serena memory, or neither.
3. Neither document names skill or agent as a destination. An agent deciding
   whether a repeatable workflow belongs in a skill, or a role-specific
   responsibility belongs in an agent template, has no checklist to read and
   guesses from directory names and precedent instead.

### Q3 Desperate Specificity

The single most blocked artifact is issue #5392, rule extraction work, which
cannot proceed until this issue lands: #5392's own description states it is
waiting on the placement contract this issue defines, and epic #5456's
sequencing table lists it as the immediate next step after #5391.

### Q4 Narrowest Wedge

Two PRs, sized separately:

1. PR A: one new section in `templates/rules/knowledge-persistence.md` (the
   placement taxonomy) plus a short pointer added to
   `.serena/memories/README.md`. About 2 hours including mirror regeneration.
2. PR B: the narrow placement validator (`scripts/validation/check_memory_placement.py`),
   its tests, and the `lefthook.yml` wiring. About 3 hours.

### Q5 Observation

Direct signals, each a file or count in this tree:

- 994 files exist under `.serena/memories/`.
- 163 of them contain the literal token `MUST` (case-sensitive);
  196 contain lowercase `must`; 214 contain `never`; 67 contain `always`.
- 92 files carry a heading (any level) matching one of
  `Constraints|Guardrails|Workflow|Procedure|Protocol|Responsibilities|Entry Criteria|Acceptance Criteria`,
  inside a surface (`.serena/memories/README.md`, "retrieval aid, non-binding")
  the repository's own rules document as never the binding source for a
  must-obey convention.
- Epic #5456's blocker table names #5391 as the sole gate in front of three
  other issues.

### Q6 Future-fit

At 10x the memory corpus (roughly 10,000 files) the contract still holds,
because it keys on activation semantics (does this content bind behavior
whenever a condition matches, independent of whether an agent happens to
retrieve it), not on file count or corpus size. A larger corpus makes the
two-signal classifier in DESIGN-026 more valuable, not less: the failure mode
it guards against (normative text landing in a surface the rules already
document as non-binding) grows linearly with corpus size, while the
classifier's per-file cost stays constant.

## Problem statement

Two rule files already tell an agent when to write a rule versus a memory
versus nothing, but neither names skill or agent as a destination, and
nothing checks that a newly written Serena memory does not itself contain the
kind of normative or procedural content the rules say a memory must never be
the sole source of. Issues #5392, #5393, and #5394 are blocked until this gap
closes.

## User stories

1. As an agent choosing where to persist a repeatable workflow, I read one
   taxonomy that names rule, skill, agent, memory, and delete-merge as the
   five destinations, so I no longer guess from directory names.
2. As a contributor adding a new Serena memory, a lefthook job warns me when
   my new file reads as normative or procedural content that belongs in a
   rule, skill, or agent instead, so the gap does not compound silently.
3. As the owner of epic #5456, I can start #5392 and #5393 once this issue's
   two PRs land, because the taxonomy and the validator both exist.

## Ontology

No OntologyFragment supplied for this issue; entities named inline from the
brief and the issue text.

- Rule: a cross-cutting normative invariant, always-on or path-scoped.
- Skill: a repeatable task, workflow, or tool-using capability invoked by
  task intent.
- Agent: a role-specific specialization, authority, or handoff contract for a
  distinct persona.
- Memory: an empirical observation, project state, measurement, incident
  record, or piece of rationale whose applicability still requires judgment.
- Delete/merge: content fully represented by an authoritative artifact, kept
  in no surface.

## Acceptance Criteria

1. WHEN an agent reads the placement taxonomy in
   `templates/rules/knowledge-persistence.md`, THE SYSTEM SHALL present five
   named destinations, rule, skill, agent, memory, and delete/merge, each with
   a one-paragraph decision rule that names what belongs there and what does
   not.
2. WHEN an agent has a new learned observation with no future required
   behavior attached, THE SYSTEM's taxonomy SHALL route it to memory.
3. WHEN an agent has a new mandatory behavior that binds every task matching a
   `paths:` scope, THE SYSTEM's taxonomy SHALL route it to a rule, path-scoped
   or always-on, or to the one skill that owns the workflow when the behavior
   binds only that skill's own invocation.
4. WHEN an agent has a repeatable workflow invoked by task intent, THE
   SYSTEM's taxonomy SHALL route it to a skill.
5. WHEN an agent has role-specific behavior, authority, or a handoff contract
   for a distinct persona, THE SYSTEM's taxonomy SHALL route it to an agent
   template.
6. WHEN a rule, skill, or agent artifact fully represents content that also
   exists in a Serena memory, and the memory carries no evidence, measurement,
   or rationale the artifact lacks, THE SYSTEM's taxonomy SHALL direct the
   agent to delete the memory rather than retain a duplicate.
7. WHEN a rule, skill, or agent overlaps a memory on the same fact, THE
   SYSTEM's taxonomy SHALL state that the rule, skill, or agent is
   authoritative and the memory is evidence that yields to it, not a second
   source of truth.

## Rationale

Epic #5456 names this issue as the sole blocker in front of three sibling
issues. The two existing persistence-surface documents already carry rule and
memory guidance; extending the same documents with the three missing
destinations, plus a narrow validator that catches the drift the corpus
measurement already shows (163 of 994 memories carry `MUST`), closes the gap
with the smallest possible change instead of building a second parallel
taxonomy.

## Dependencies

- DESIGN-026 depends on this requirement.
- Blocks issue #5392 (rule extraction), issue #5393, and issue #5394
  transitively, per epic #5456's sequencing.
- Extends `templates/rules/knowledge-persistence.md` and
  `.serena/memories/README.md`; does not replace either.

## Out of scope

- A capability registry or ownership graph across rules, skills, agents, and
  memories. Deferred to issue #5396, past v0.7.0.
- A general Markdown duplication or quality framework across the repository.
  Owned by issue #5397.
- A context or token growth ratchet or budget. Owned by issue #5400.
- Any change to the existing memory-index integrity validators: orphan and
  unindexed detection (issue #4313), the inert-prose check (issue #4776), or
  the duplicate-target-paths check (issue #4705). This issue adds a new,
  separate validator; it does not modify those three.
- A copied-contract evidence policy. Owned by issue #5399.
- A second, parallel taxonomy. This issue extends
  `templates/rules/knowledge-persistence.md` and `.serena/memories/README.md`;
  it does not create a competing document.
- Editing `templates/rules/universal.md`. Epic #5456's direction (2026-09-11)
  states any byte change to an always-on rule needs figures refreshed in four
  downstream documents, so this work leaves that file untouched and extends
  the path-scoped `knowledge-persistence.md` instead.
- Migrating the existing 994-file memory corpus. Existing memories are warned
  by the validator, never failed; only newly added memories can fail.

## Deferred

- Retroactively reclassifying any of the 163 existing memories that contain
  `MUST`. Owner: whoever picks up issue #5397's general duplication and
  quality framework, which is the right scope for a corpus-wide pass.
- Extending the validator's two-signal classifier with additional signals
  beyond the four in DESIGN-026, if the false-positive or false-negative rate
  measured after 30 real runs warrants it. Owner: the maintainer of
  `scripts/validation/check_memory_placement.py`.

## Open questions

None blocking.

## CVA summary

- **Common**: every one of the five destinations (rule, skill, agent, memory,
  delete/merge) answers the same question, where does this content live so
  the next reader finds it, and each is chosen by asking whether the content
  is normative-and-scoped, procedural-and-invoked-by-intent,
  role-specific-and-persona-bound, observational-and-judgment-dependent, or
  redundant.
- **Varies**: the activation mechanism per destination (always-on or
  path-scoped for rules, task-intent invocation for skills, persona
  assignment for agents, retrieval for memories) and the authority each
  carries when it conflicts with another surface.
- **Relationships**: memory is always subordinate to rule, skill, or agent
  when the same fact appears in both; the taxonomy names this a yield
  relationship, not a merge. Delete/merge is not a sixth kind of content, it
  is the disposition applied once a memory's content is fully absorbed by one
  of the other four.

## Buy-vs-build decision

N/A (doc + narrow validator extending existing hook infrastructure)

## Complexity classification

- Engineering tier: 2.
- Cynefin domain: Clear. The taxonomy and the validator's four signals were
  both fully specified before this requirement was written; nothing here is
  emergent or requires expert diagnosis to apply.
