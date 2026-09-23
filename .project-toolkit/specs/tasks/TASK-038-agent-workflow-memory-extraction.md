---
type: task
id: TASK-038
title: Extract the agent-workflow memory family into its skill and agent owners
status: todo
priority: P1
complexity: M
source: GH-5393
related:
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

# TASK-038: Extract the agent-workflow memory family into its skill and agent owners

## Objective

Ship the one PR DESIGN-027 defines: three owner edits, ten memory
dispositions, index cleanup, and the checked-in inventory for every
`agent-workflow/`, `autonomous/`, and `skills-*-index.md` family.

## Milestone 1: owners carry the content (S)

Exit: `uv run python build/scripts/build_all.py --check` exits 0.

1. Edit `templates/agents/orchestrator.shared.md` Routing Algorithm step 4
   (REQ-029 AC1). Done when the rendered `.claude/agents/orchestrator.md`
   names `critic (plan gate)` between `milestone-planner` and `implementer`.
2. Edit `templates/agents/critic.shared.md` Handoff (AC2). Done when no
   `planner` route remains in the rendered critic agent.
3. Add `.claude/skills/git-advanced-workflows/references/worktree-triage.md`
   and the trigger, Phase 2, and anti-pattern rows in the skill template
   (AC3). Done when `orphan-ref-validator` passes and the reference names the
   age check, file-list check, PR join, and anchor step.

## Milestone 2: memories yield to owners (S)

Exit: `memory_index.py --ci` and `check_memory_placement.py --ci` pass.

4. Delete `agentworkflow-004-proactive-template-sync-verification-95.md` and
   `agent-generation-edit-locations.md` (AC4). Done when no index or memory
   links to either name.
5. Thin the seven files DESIGN-027 marks "Thin" to a `placement: evidence`
   memory that names the owner (AC4). Done when each file keeps its measured
   evidence and no procedure.
6. Update `skills-agent-workflow-index.md`, `memory-index.md`, and
   `learning-index.md` rows (AC5). Done when every row resolves.

## Milestone 3: inventory (S)

Exit: `.project-toolkit/analysis/5393-serena-workflow-inventory.md` exists.

7. Write one row per `agent-workflow/` and `autonomous/` file and one row per
   `skills-*-index.md` family (AC6). Done when 13 + 6 + 34 rows are present
   and each names an owner the auditor opened or says `none found`.

## Dependency graph

```text
1, 2, 3 (parallel) -> 4, 5, 6 -> 7
```

## Done definition

- REQ-029 AC1 through AC8 each map to a named hunk in the PR.
- PR body carries the inventory path and the local gate commands run.
- Handoff to the downstream Serena thinning issue lists the `already-owned`
  families.
