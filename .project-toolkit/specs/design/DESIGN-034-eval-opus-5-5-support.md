---
type: design
id: DESIGN-034
title: Run the eval harness on Claude Opus 5.5
status: implemented
priority: P2
related:
  - REQ-036
  - TASK-045
created: 2026-09-24
updated: 2026-09-24
author: spec-generator
tags:
  - eval
  - orchestrator
---

# DESIGN-034: Run the eval harness on Claude Opus 5.5

## Requirements Addressed

REQ-036 criteria 1 to 6.

## Diagnosis

Opus 5.5 needs no transport change. It rejects `temperature`, and
`call_with_temperature_fallback` already retries without it. Thinking cannot
be disabled, so thinking tokens share the 1,024-token budget. A 2026-09-24
baseline of the orchestrator corpus parsed 84 of 84 responses, so the budget
stays.

The gate failed on wording. S8, S9, and S13 answered STOP in 6 of 6 runs. Some
reasons said "done" or "complete" instead of `terminal`, or never said
`side quest`.

## Change

- `_eval_common.py` gains `claude-opus-5-5` and `claude-opus-5.5` rows at
  $0.004 input and $0.020 output per 1K tokens. The rate comes from the
  Claude API model table. Two rows are needed because the lookup is an exact
  key match and each harness accepts one spelling.
- `owner-copilot-cli.json` gains an `opus55` reference tier on
  `claude-opus-5.5`.
- S8, S9, and S13 drop `expected_reason_contains`. STOP against CONTINUE,
  DELEGATE, and ASK still grades the decision, as S10 does after PR #5908.
  S12 keeps its `terminal` check because it passed 6 of 6 on Opus 5.5.
- `test_pricing_coverage.py` pins both Opus 5.5 rates and checks that every
  spelling pair of one model carries one rate, using `harness_model_id`.

## Alternatives Rejected

- One row plus spelling normalization in the price lookup. It touches every
  cost caller for a two-row gain.
- Raising `max_tokens`. No truncation was observed, and a larger budget
  raises the cost of every run on every model.
