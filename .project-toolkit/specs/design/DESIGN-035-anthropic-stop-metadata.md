---
type: design
id: DESIGN-035
title: Keep stop metadata from Claude responses in the eval adapter
status: implemented
priority: P2
related:
  - REQ-037
  - TASK-046
created: 2026-09-24
updated: 2026-09-24
author: spec-generator
tags:
  - eval
  - anthropic
---

# DESIGN-035: Keep stop metadata from Claude responses in the eval adapter

## Requirements Addressed

REQ-037 criteria 1 to 10.

## Change

- `_anthropic_api.py` gains `MessageResponse`, `classify_termination`, and
  `parse_message_response`. The parser reads the response dict once.
- `call_api_response` holds the request logic and returns a
  `MessageResponse`. A non-default provider yields termination `unknown`.
- `call_api` calls `call_api_response` and returns its text. When the caller
  passes `metadata`, it also writes `termination` and `stop_reason`, and
  `refusal_category` on a refusal. Existing text-only callers see no change.
- `_eval_api_adapter.py`: `APICallResult` gains `termination`. The
  Anthropic transport records the termination it read. A `refusal`,
  `token_limit`, or `incomplete` result returns `outcome="error"` with a new
  error category and is not retried. The adapter takes `max_tokens` and
  passes it to both transports.
- `eval-rule-activation.py`: the judge fails on a `refusal`, `token_limit`,
  or `incomplete` termination and records it in the sample.
- `eval-prompt-change.py`: the judge reads the termination through
  `metadata` and returns a `not_scored` result on `refusal`, `token_limit`,
  or `incomplete`. `run_scenario_multi` excludes such runs from its scored
  run count instead of counting them as a failed run; a scenario with zero
  scored runs cannot pass.

## Alternatives Rejected

- Change `call_api` to return `MessageResponse`. About 14 callers read a
  string; each would need a migration for no gain in this issue.
- Raise from `call_api` on a refusal. Text-only callers would change
  behavior without an explicit migration.
- Raise the 1,024-token default. The termination field shows whether a
  budget is too small; a global raise costs every run on every model.
