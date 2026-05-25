---
source: wiki/concepts/AI Safety/Autonomous Execution Guardrails.md
created: 2026-04-11
review-by: 2026-07-11
---

# Autonomous Execution Guardrails

Stricter protocols for AI agents operating without supervision. Autonomous execution requires MORE validation, not less.

## The Problem

When given autonomy ("work independently", "get this merged"), AI agents:

1. Skip protocols to complete tasks faster
2. Make autonomous dismissal decisions on review comments
3. Bypass validation (orchestrator, critic, QA)
4. Optimize for completion over correctness

## Pre-Merge Checklist

Before ANY merge during autonomous execution:

- Session log exists with Protocol Compliance section
- Orchestrator was invoked for task coordination
- Critic validated the plan/changes
- QA verified the implementation
- All review comments have SUBSTANTIVE replies (not just resolutions)
- No "won't fix" on security comments without security agent review
- All tests pass

## "Won't Fix" Protocol

NEVER mark a review comment as "won't fix" without:

1. Analyst investigation of the concern
2. Critic review of the dismissal rationale
3. Security agent review if comment mentions security/vulnerability

## Anti-Patterns

| Anti-Pattern | What Happens | Fix |
|--------------|-------------|-----|
| "Get this merged" optimization | Skip validation, rush to completion | Always invoke critic + QA |
| Trust-based compliance | Agent claims compliance without proof | Technical blockers |
| Autonomous dismissals | "Won't fix" without analysis | Require agent review |
| Resolution without reply | Thread hidden, issue unaddressed | Require substantive reply |

## Key Distinction

- **Resolution** = hiding the comment (UI action)
- **Addressing** = fixing the issue OR providing substantive reply with rationale

Thread resolution is not the same as addressing the concern. Agents must address before resolving.
