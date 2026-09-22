---
type: requirement
id: REQ-029
title: Extract reusable workflows and role contracts from Serena memories into skills and agents
status: draft
priority: P1
category: functional
source: GH-5393
epic: EPIC-5456
related:
  - REQ-028
  - DESIGN-027
created: 2026-09-21
updated: 2026-09-21
author: spec
tags:
  - governance
  - memory
  - knowledge-persistence
  - skills
  - agents
---

# REQ-029: Extract reusable workflows and role contracts from Serena memories into skills and agents

## Step 0 First Principles

### Q1 Demand Reality

1. Issue #5393's author, `rjmurillo`, opened the issue and added the
   reconciliation comment that scopes it to migration by composition.
2. Epic #5456 sequences #5393 as Phase 2B after #5391 and names it a blocker
   for the final Serena thinning issue.
3. Issue #5391's acceptance criteria state that the migration issues depending
   on the placement contract "can execute without making new taxonomy
   decisions"; #5393 is one of those two issues.

### Q2 Status Quo

An agent that wants the multi-agent pipeline, the critic gate, or the
worktree-triage procedure today finds them only by querying Serena for
`skills-agent-workflow-index.md` or `memory-index.md`. The first-class owners
(`templates/agents/orchestrator.shared.md`, the `plan` skill, the
`git-advanced-workflows` skill) carry a partial copy or none, so the two copies
drift and the procedure runs only when the memory is retrieved.

### Q3 Desperate Specificity

The downstream Serena thinning issue cannot delete or thin the 13 files under
`.serena/memories/agent-workflow/` until each one has a named first-class
owner. `agent-generation-edit-locations.md` is the most costly case: it states
that `.claude/agents/` is hand-maintained, which ADR-109 B1 made false, so an
agent that retrieves it edits generated output that the next build overwrites.

### Q4 Narrowest Wedge

One PR, about 4 hours AI-assisted:

1. Extend the three owners that lack the Serena content: the orchestrator
   routing algorithm (critic plan gate), the critic handoff (name the
   registered planner agent), and `git-advanced-workflows` (worktree triage
   reference).
2. Thin or delete the 13 `agent-workflow/` memories, fix their index rows.
3. Record the per-file inventory for `agent-workflow/`, `autonomous/`, and the
   34 `skills-*-index.md` families in a checked-in analysis artifact.

### Q5 Observation

- 13 files under `.serena/memories/agent-workflow/`; 3 already carry the
  `placement: evidence` marker from #5392, 10 do not.
- 6 files under `.serena/memories/autonomous/`; all 6 carry the marker.
- 34 top-level `skills-*-index.md` files index 380 memories totalling about
  28,000 lines; 171 of the 380 contain a normative term.
- The `Related` lists in `agent-workflow/agent-workflow-pipeline.md`,
  `agent-workflow-critic-gate.md`, `agent-workflow-collaboration.md`,
  `agent-workflow-observations.md`, and
  `agent-workflow-post-implementation-critic-validation.md` point at
  `agent-workflow-004-proactive-template-sync-verification.md` and
  `agent-workflow-005-structured-handoff-formats.md`, which do not exist.
- `templates/agents/critic.shared.md:236` routes `NEEDS_REVISION` to
  `planner`, an agent that is not registered; the registered agents are
  `milestone-planner` and `task-decomposer`.

### Q6 Future-fit

At 10x the memory corpus the contract still holds: every procedure has one
owner in `.claude/skills/` or `templates/agents/`, and Serena holds only the
evidence for why it exists. More memories add more evidence rows, not more
procedural copies.

## Problem statement

Repeatable procedures and role contracts live in Serena memories that activate
only on retrieval, while the first-class skills and agents that should own them
carry partial or stale copies. Each `agent-workflow/` memory needs a named
owner, the owner needs the missing content, and the memory must shrink to
evidence.

## User stories

1. As an orchestrator session, I read the critic plan gate in my own routing
   algorithm, so the gate runs without a Serena lookup.
2. As an agent triaging a stale worktree, I invoke `git-advanced-workflows`
   and find the live-versus-abandoned procedure with its anchor-before-remove
   step, so I do not freeze an issue or drop an unreachable tip.
3. As the owner of the downstream thinning issue, I read one inventory that
   names the class, owner, and residual action for every `agent-workflow/`,
   `autonomous/`, and `skills-*-index.md` family, so I do not reclassify.

## Ontology

Uses REQ-028's five classes (rule, skill, agent, memory, delete/merge)
unchanged. Adds no new class and no capability metadata; issue #5396 owns
ownership and dependency metadata.

## Acceptance Criteria

1. WHEN the orchestrator's Routing Algorithm names the standard lifecycle
   sequence, THE SYSTEM SHALL place a critic plan gate between the planning
   role and `implementer`, and SHALL name the verdict routes (`APPROVED` to
   `implementer`, `NEEDS_REVISION` back to the planning role, `BLOCKED` to
   the orchestrator).
2. WHEN the critic's Handoff names the return route for `NEEDS_REVISION`,
   THE SYSTEM SHALL name a registered agent (`milestone-planner` or
   `task-decomposer`), not `planner`.
3. WHEN an agent invokes `git-advanced-workflows` for a stale worktree, THE
   SYSTEM SHALL provide a reference that carries the age check, the file-list
   check, the pull-request join, and the anchor-before-remove step.
4. WHEN a file under `.serena/memories/agent-workflow/` carries content that a
   rule, skill, or agent now owns, THE SYSTEM SHALL either delete it or thin it
   to a `placement: evidence` memory that names the owner.
5. WHEN a memory under `agent-workflow/` or `autonomous/` is deleted or
   renamed, THE SYSTEM SHALL leave no dangling link in `memory-index.md`,
   `learning-index.md`, or any `skills-*-index.md`, and
   `memory_index.py --ci` SHALL pass.
6. WHEN the inventory artifact is read, THE SYSTEM SHALL list every file under
   `agent-workflow/` and `autonomous/` individually, and every one of the 34
   `skills-*-index.md` families, each with class, existing destination,
   action, and residual memory action.
7. WHEN `uv run python build/scripts/build_all.py --check` runs on the
   branch head, THE SYSTEM SHALL exit 0, so every agent and skill mirror
   matches its template.
8. WHEN `check_memory_placement.py --ci` runs against the branch, THE SYSTEM
   SHALL report no failure for the thinned memories.

## Rationale

The issue's own comment prefers composition over migration-by-copy. Reading
every owner first showed that autoplan, the orchestrator, the plan skill, the
build exit gates, and the role agents already own most of the `agent-workflow/`
content. The gaps are three small edits, one stale memory that misdirects
edits to generated files, and a worktree-triage procedure with no owner.

## Dependencies

- REQ-028 (placement contract) landed as `94189bbcb` and `ee9a490e6`.
- Issue #5392 landed as `78f058654` and `49d28a545`; it thinned
  `autonomous/` and three `agent-workflow/` files to evidence.
- Issue #5396 is open: this requirement adds no capability, ownership, or
  dependency metadata to any skill or agent.

## Out of scope

- Per-file thinning of the 380 memories under the 34 `skills-*-index.md`
  families. This requirement inventories and classifies each family and hands
  the thinning to the downstream Serena thinning issue.
- Capability frontmatter, dependency edges, or an ownership registry (#5396).
- A prompt-quality or duplication framework (#5397), evidence contracts
  (#5399), or context-size measurement (#5400).
- Rewriting agents or skills beyond the three named edits.
- Deleting `skills-*-index.md` infrastructure still used by non-migrated
  memories.

## Deferred

- Thinning the families the inventory marks `already-owned`. Owner: the
  downstream Serena thinning issue named by epic #5456.
- Adopting `agentskills.io` `compatibility` and `allowed-tools` fields. Owner:
  the `skillforge` skill maintainer; the memory stays as reference.

## Open questions

None blocking.

## CVA summary

- **Common**: every candidate memory answers the same three questions: who
  owns the behavior, what does the owner lack, what evidence stays.
- **Varies**: the owner class (skill for procedures, agent for handoffs) and
  the residual action (delete when stale, thin when evidence remains).
- **Relationships**: the memory yields to the owner on every overlap; the
  inventory is the record of each yield.

## Buy-vs-build decision

N/A (migration and doc change inside existing skills and agents)

## Complexity classification

- Engineering tier: 2.
- Cynefin domain: Clear. The placement contract fixes the classes; the work
  is reading each source and applying the table.
