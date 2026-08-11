---
type: task
id: TASK-020
title: Build Aspire skill decision matrix
status: todo
priority: P1
complexity: L
related:
  - DESIGN-019
blocked_by:
  - TASK-019
blocks:
  - TASK-021
created: 2026-08-11
updated: 2026-08-11
author: task-decomposer
tags:
  - skills
  - skillforge
  - analysis
---

# TASK-020: Build Aspire skill decision matrix

## Objective

Classify every Aspire skill against local skills, agents, and commands, then
record a cited keep, augment, compose, create, or reject decision.

## In/Out of Scope

**In scope:**

- Source purpose, triggers, workflow, gates, tools, outputs, and product coupling.
- Local owner and SkillForge score.
- Reusable idea or workflow classification.
- One decision and rationale per source skill.

**Out of scope:**

- Skill edits.
- Direct Aspire product skill ports.
- Generic review framework design.

## Acceptance Criteria

- [ ] Matrix row count equals the source skill count.
- [ ] Every retained idea has a pinned source citation.
- [ ] Skills, agents, and commands are checked before creation.
- [ ] SkillForge thresholds determine the route.
- [ ] At most one candidate is marked create.
- [ ] Aspire product-operation skills are rejected.
- [ ] REQ-020 co-change checklist wildcards are replaced with exact selected
      canonical and generated paths before TASK-021 starts.

## Files Affected

| File | Action | Description |
|---|---|---|
| `.agents/analysis/aspire-skill-review-matrix.md` | Create | Human-readable decision matrix |
| `.agents/analysis/aspire-skill-review-matrix.json` | Create | Machine-readable decisions and scores |

## Implementation Notes

Consume `.agents/analysis/aspire-skill-source-files.json` from TASK-019 as the
source count and path authority.

Likely mappings to verify:

- `issue-investigation`: compose or augment GitHub, analysis, and debugging.
- `ci-test-failures`: augment GitHub CI tooling or debugging playbook.
- `cli-e2e-testing`: augment QA evidence guidance when gaps exist.
- `pr-testing`: consider creation only when no existing owner remains.
- `test-management`: reject until local quarantine infrastructure exists.

## Testing Requirements

- Positive: every source skill receives one valid decision.
- Negative: a known local owner prevents create.
- Edge: a source skill with mixed generic and product-specific content splits
  the retained idea from rejected commands.
