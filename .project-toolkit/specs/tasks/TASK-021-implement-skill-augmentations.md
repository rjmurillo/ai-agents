---
type: task
id: TASK-021
title: Implement approved skill augmentations
status: todo
priority: P1
complexity: M
related:
  - DESIGN-019
blocked_by:
  - TASK-020
blocks:
  - TASK-022
created: 2026-08-11
updated: 2026-08-11
author: task-decomposer
tags:
  - skills
  - implementation
---

# TASK-021: Implement approved skill augmentations

## Objective

Apply the decision matrix to canonical local skills with the smallest working
change set.

## In/Out of Scope

**In scope:**

- Existing skill updates.
- At most one verified new generic skill.
- Progressive-disclosure references.
- Required structure tests.

**Out of scope:**

- Hand-edited Copilot mirrors.
- New dependencies.
- Aspire-specific commands or policy.
- Unapproved matrix candidates.

## Acceptance Criteria

- [ ] Every edit traces to an approved matrix row.
- [ ] Existing skills are preferred over creation.
- [ ] No more than one new skill is created.
- [ ] `SKILL.md` stays concise and uses progressive disclosure.
- [ ] New skill frontmatter, triggers, scope, process, and verification pass
      SkillForge checks.

## Files Affected

| File | Action | Description |
|---|---|---|
| `.claude/skills/<selected>/SKILL.md` | Modify | Approved generic workflow guidance |
| `.claude/skills/<selected>/references/*.md` | Create or modify | Detailed evidence patterns |
| `.claude/skills/<new-skill>/tests/test_skill_structure.py` | Create if needed | Colocated structure checks required by the skill rule |
| `tests/skills/<new-skill>/test_<behavior>.py` | Create if needed | Default-collected behavior tests for skill scripts |

## Implementation Notes

Do not build a source-review framework. Copy no Aspire commands. Cite Aspire as
inspiration for retained generic ideas.

## Testing Requirements

- SkillForge quick and full validation.
- Colocated structure tests for any new skill.
- Default-collected behavior tests for any new or changed skill script.
- Reference-link and size checks.
