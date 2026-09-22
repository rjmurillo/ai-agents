---
type: design
id: DESIGN-027
title: Composition-first extraction of the agent-workflow memory family
status: draft
priority: P1
related:
  - REQ-029
  - TASK-038
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

# DESIGN-027: Composition-first extraction of the agent-workflow memory family

## Requirements Addressed

REQ-029 acceptance criteria 1 through 8, per
`.agents/specs/requirements/REQ-029-serena-workflows-to-skills-and-agents.md`.

## Existing owners (verified by reading each file)

| Serena concept | Owner today | Gap |
|---|---|---|
| Size-tiered pipeline depth | `.claude/skills/autoplan/SKILL.md` tier table (Trivial, Standard, Feature) | None |
| Role sequence and handoff contract | `templates/agents/orchestrator.shared.md` Routing Algorithm step 4 and Handoff Contract | Step 4 omits the critic plan gate the `plan` skill runs at step 7 |
| Pre-implementation critic gate | `.claude/skills/plan/SKILL.md` step 7; `templates/agents/critic.shared.md` Review Axes | Critic handoff routes `NEEDS_REVISION` to `planner`, an unregistered name |
| Post-implementation convention check | `.claude/skills/build/SKILL.md` four exit gates; `review` skill axes | None |
| Structured handoff tables | Orchestrator Handoff Contract; each role's `## Handoff` section | None |
| Template-sync before commit | `.claude/rules/generated-artifacts.md`, `build_all.py --check` | None; two memories describe the pre-ADR-109 layout and are wrong |
| User additions as learning signals | `reflect` skill description | None |
| Fleet worktree triage | `git-advanced-workflows` skill (worktree add and remove only) | No live-versus-abandoned procedure, no anchor-before-remove step |
| agentskills.io compatibility | `skillforge` skill owns skill authoring | None; memory stays as external reference |

## Design

Three owner edits, each the smallest change that closes its gap:

1. `templates/agents/orchestrator.shared.md`, Routing Algorithm step 4: insert
   `critic (plan gate)` between `milestone-planner` and `implementer`, and add
   one line naming the three verdict routes. The autoplan tier table keeps
   ownership of when the lifecycle runs at all.
2. `templates/agents/critic.shared.md`, Handoff: `NEEDS_REVISION` returns to
   `milestone-planner` or `task-decomposer`, whichever produced the plan.
3. `git-advanced-workflows`: add `references/worktree-triage.md` (hand-kept
   support file under `.claude/skills/`), one trigger row, one Phase 2
   subsection that points at the reference, and one anti-pattern row in
   `templates/skills/git-advanced-workflows.SKILL.md.tmpl`.

Memory dispositions for the 13 `agent-workflow/` files:

| File | Action | Owner named in residual |
|---|---|---|
| `agent-workflow-pipeline.md` | Thin to evidence (59-file change, zero rollbacks) | autoplan tiers, orchestrator step 4 |
| `agent-workflow-critic-gate.md` | Thin to evidence (three issues caught) | plan step 7, critic Review Axes |
| `agent-workflow-post-implementation-critic-validation.md` | Thin to evidence (session 87, commit 5a65f65) | build exit gates, review |
| `agentworkflow-005-structured-handoff-formats-88.md` | Thin to evidence (session 17) | orchestrator Handoff Contract |
| `agentworkflow-004-proactive-template-sync-verification-95.md` | Delete: pre-ADR-109 layout; its evidence lives in `agent-workflow-collaboration.md` | generated-artifacts rule |
| `agent-generation-edit-locations.md` | Delete: states `.claude/agents/` is hand-maintained, false since ADR-109 B1; PR #1715 evidence lives in `decision-agent-files-are-not-canonical.md` | generated-artifacts rule |
| `agent-workflow-collaboration.md` | Thin to evidence (P2-6 addition) | reflect skill |
| `agent-workflow-observations.md` | Thin: drop empty Constraints and Preferences scaffolding, keep the two observations and history | AGENTS.md routing (model for CI) |
| `agentskills-io-standard-integration.md` | Unchanged: external reference | skillforge |
| `fleet-worktree-live-versus-abandoned.md` | Thin to measurements and incident | git-advanced-workflows reference |
| `agent-workflow-atomic-commits.md`, `-mvp-shipping.md`, `-scope-discipline.md` | Unchanged (#5392) | Universal Rules |

The six `autonomous/` files stay unchanged; #5392 already thinned each to
evidence with a `placement: evidence` marker.

The 34 `skills-*-index.md` families get one inventory row each in
`.agents/analysis/5393-serena-workflow-inventory.md`: class, existing owner,
action, residual. Thinning them is out of scope (REQ-029).

## Risk register (pre-mortem)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Deleting a memory leaves a dangling index row | Medium | `memory_index.py --ci` fails the commit | Grep every index for each deleted name before commit; run the CI command locally |
| Thinned memory still trips the placement check | Low | pre-commit warns (existing files only warn) | Add the `placement: evidence` marker with a reason to each thinned file |
| Orchestrator edit breaks a mirror | Low | `build_all.py --check` exit 2 | Run `build_all.py` after every template edit; commit the rendered copies |
| Worktree reference carries a repo-only path literal | Medium | portability ratchet fires | Cite memories by name, not path; no `.serena/` or `.agents/` literals in the reference |
| Inventory rows assert an owner nobody opened | Medium | reviewer rejects unverified claim | Each row cites a file the auditor opened; unknown owners say `none found` with search terms |

## Deferred

- Thinning the `already-owned` families: downstream Serena thinning issue.
- `agentskills.io` `compatibility` and `allowed-tools` fields: skillforge.
- Capability metadata for any edited skill or agent: #5396.
