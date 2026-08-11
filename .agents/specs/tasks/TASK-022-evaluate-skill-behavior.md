---
type: task
id: TASK-022
title: Evaluate changed skill behavior
status: todo
priority: P1
complexity: L
related:
  - DESIGN-019
blocked_by:
  - TASK-021
blocks:
  - TASK-023
created: 2026-08-11
updated: 2026-08-11
author: task-decomposer
tags:
  - skills
  - eval
  - copilot
---

# TASK-022: Evaluate changed skill behavior

## Objective

Prove that each judgment-bearing skill change does not regress the intended
behavior under the local Copilot CLI provider. Record improvement separately.

## In/Out of Scope

**In scope:**

- Positive, negative, and edge scenarios.
- Baseline and candidate comparison.
- Three runs per scenario.
- Eval reports with deltas and regressions.
- Deterministic tests for utility-only changes.

**Out of scope:**

- Cross-provider score comparison.
- P50 PR review rounds as a release gate.
- Raw Copilot process output in durable reports.

## Acceptance Criteria

- [ ] Dry-run validates every scenario before provider calls.
- [ ] `eval-prompt-change.py --provider copilot` is used for base and
      working-copy prompts.
- [ ] Every judgment-bearing changed skill runs three times per scenario.
- [ ] Every prompt-change acceptance gate returns PASS.
- [ ] Every report records delta, improvements, regressions, and
      `has_improvement` for human review.
- [ ] Scenario coverage includes at least one positive case, one negative case
      for duplicate creation, one negative case for missing source identity,
      and one edge case for product-specific rejection.
- [ ] Utility-only changes have deterministic tests instead of model evals.

## Files Affected

| File | Action | Description |
|---|---|---|
| `tests/evals/skills/aspire-skill-review-scenarios.json` | Create | Skill behavior scenarios |
| `evals/reports/aspire-skill-review-<run-id>.json` | Create | Eval output |
| `evals/reports/aspire-skill-review-<run-id>.md` | Create | Human-readable result |

## Implementation Notes

Keep the provider constant within the run. Use verdict scenarios that detect
duplicate creation, product-specific copying, and missing source identity.
Eval spend is authorized. Do not reduce required coverage to save provider
cost.

## Testing Requirements

- Baseline control.
- Candidate treatment.
- Negative control that fails when the source pin or overlap gate is removed.
- Tie handling that marks improvement unproved.
