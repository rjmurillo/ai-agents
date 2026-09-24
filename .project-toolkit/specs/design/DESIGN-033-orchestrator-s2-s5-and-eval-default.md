---
type: design
id: DESIGN-033
title: Grade orchestrator S2 and S5 on the decision, and move the eval default to Sonnet 5
status: implemented
priority: P2
related:
  - REQ-035
  - TASK-044
created: 2026-09-24
updated: 2026-09-24
author: spec-generator
tags:
  - eval
  - orchestrator
---

# DESIGN-033: Grade orchestrator S2 and S5 on the decision, and move the eval default to Sonnet 5

## Requirements Addressed

REQ-035 criteria 1 to 6.

## Diagnosis

The S2 regression that PR #5904 recorded is model-specific. On
`claude-sonnet-4-6`, the current prompt answered ASK. On `claude-sonnet-5`,
the same prompt routes to analyst for investigation and labels it DELEGATE.
S5 answered DELEGATE to the security agent on both models, on both the old and
current prompt. So no prompt text causes either failure. The scenarios offer
two labels for one action.

A prompt edit was considered: restore "route to analyst first" in the
unknowns row. It is not needed on the default model, and the Copilot
orchestrator prompt sits 15 characters under its 30,000-character cap. It is
not made.

## Change

- S2 and S5 drop DELEGATE from `verdict_options`. Their reason checks stay
  and still reject a reason that names no investigation or no security
  review. S1, S3, and S4 offered the same synonym pair; S1 answered DELEGATE
  once on `claude-sonnet-5`. They drop DELEGATE too, and keep their reason
  checks (`analyst`, `spec`, `security`).
- S2's reason check becomes the stem `investigat`. On `claude-sonnet-5`, S2
  answered ROUTE in 6 of 6 runs but passed 2, because 4 reasons said
  "investigation", which the literal `investigate` does not match.
- S10 drops its `optional` phrase check. On `claude-sonnet-5` it answered
  STOP in 6 of 6 runs but passed 1: the reasons said "out of scope",
  "unrequested", or "not in the frozen contract". STOP against CONTINUE and
  DELEGATE still grades the decision, as critic TC-1 and orchestrator S11
  already do after PR #5904.
- `DEFAULT_MODEL` becomes `claude-sonnet-5`. The routing policy assigns
  specified judgment to Sonnet 5.
- `_eval_common.py` gains a `claude-sonnet-5` row: $0.002 input and $0.010
  output per 1K tokens.
