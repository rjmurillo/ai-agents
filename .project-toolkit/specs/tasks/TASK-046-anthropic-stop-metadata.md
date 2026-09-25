---
type: task
id: TASK-046
title: Keep stop metadata from Claude responses in the eval adapter
status: implemented
priority: P2
related:
  - REQ-037
  - DESIGN-035
created: 2026-09-24
updated: 2026-09-24
author: plan
tags:
  - eval
  - anthropic
---

# TASK-046: Keep stop metadata from Claude responses in the eval adapter

## Steps

1. Add `MessageResponse`, `classify_termination`, and
   `parse_message_response` to `scripts/eval/_anthropic_response.py`. Add
   `call_api_response` to `scripts/eval/_anthropic_api.py`. Make `call_api`
   a text view with the metadata write-through.
2. Add unit tests for `end_turn`, `refusal`, `max_tokens`, mixed thinking
   and text blocks, unknown stop reasons, a non-default provider, and the
   `max_tokens` pass-through.
3. Add `termination`, the refusal and token-limit error categories, and the
   `max_tokens` parameter to `scripts/eval/_eval_api_adapter.py`, with
   tests.
4. Make the judges in `eval-rule-activation.py` and `eval-prompt-change.py`
   refuse to score a `refusal`, `token_limit`, or `incomplete` response,
   with tests.
5. Run the eval test suite, ruff, and mypy on the changed files.

## Done When

Every REQ-037 acceptance criterion maps to a passing test.
