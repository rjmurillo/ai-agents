---
type: task
id: TASK-023
title: Regenerate and validate skill artifacts
status: todo
priority: P1
complexity: M
related:
  - DESIGN-019
blocked_by:
  - TASK-022
created: 2026-08-11
updated: 2026-08-11
author: task-decomposer
tags:
  - skills
  - generation
  - validation
---

# TASK-023: Regenerate and validate skill artifacts

## Objective

Generate shipped Copilot skill copies and clear every targeted repository gate.

## In/Out of Scope

**In scope:**

- Build generation.
- Expected diff review.
- Skill, test, drift, portability, dash, and pre-PR validation.
- Final source-to-local decision report.

**Out of scope:**

- Hand edits under `src/copilot-cli/skills/`.
- Plugin manifest version changes.
- Unrelated cleanup.

## Acceptance Criteria

- [ ] `build_all.py` regenerates the expected skill copies.
- [ ] No unrelated generated files change.
- [ ] Canonical and generated skills match.
- [ ] SkillForge and targeted tests pass.
- [ ] Portability, dash, reference, and drift checks pass.
- [ ] Every new durable analysis and eval artifact is transformed through
      `scripts/redact_secrets.py` into a sanitized file before commit.
- [ ] Only the sanitized file replaces the original after a targeted scan finds
      no unredacted SAML authorization URLs, emails, or internal hostnames.
- [ ] `pre_pr.py` exits 0.
- [ ] Final report records every source decision and eval verdict.

## Files Affected

| File | Action | Description |
|---|---|---|
| `src/copilot-cli/skills/<selected>/SKILL.md` | Generate | Shipped skill copy |
| `src/copilot-cli/skills/<selected>/references/*.md` | Generate | Shipped references |
| `.agents/analysis/aspire-skill-review-final.md` | Create | Final matrix and validation evidence |

## Implementation Notes

Run generation from canonical sources. Inspect the diff before validation.

## Testing Requirements

- Targeted changed-skill tests.
- Generated drift checks.
- Portability checks.
- `uv run python scripts/validation/pre_pr.py`.
