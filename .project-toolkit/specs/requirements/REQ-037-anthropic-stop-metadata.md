---
type: requirement
id: REQ-037
title: Keep stop metadata from Claude responses in the eval adapter
status: implemented
priority: P2
category: functional
source: issue-5902
related:
  - DESIGN-035
  - TASK-046
  - REQ-036
created: 2026-09-24
updated: 2026-09-24
author: spec
tags:
  - eval
  - anthropic
---

# REQ-037: Keep stop metadata from Claude responses in the eval adapter

## Step 0 First Principles

### Q1 Demand Reality

Issue #5902, filed by rjmurillo. REQ-036 and DESIGN-034 name the gap: the
adapter drops `stop_reason`, so an Opus 5.5 run cannot show whether a
response hit the token limit. The owner asked on 2026-09-24 to ship #5902.

### Q2 Status Quo

`call_api` in `scripts/eval/_anthropic_api.py` joins the `text` blocks and
returns a string. A refusal, a truncated answer, and a full answer all
reach the grader as plain text. An operator who suspects truncation must
rerun the prompt by hand with `curl` and read `stop_reason`.

### Q3 Desperate Specificity

The prompt-change acceptance gate on the orchestrator corpus. It runs on
`claude-opus-5-5` and `claude-sonnet-5`, both with adaptive thinking that
shares the 1,024-token budget. The gate cannot tell a cut-off verdict from a
wrong one.

### Q4 Narrowest Wedge

About 2 hours: a structured result in `_anthropic_api.py`, a metadata
write-through in `call_api`, termination handling in the three evaluators
that already route metadata or feed a gate, and unit tests.

### Q5 Observation

DESIGN-034 records that the 2026-09-24 baseline "cannot show whether a
response hit the limit after its verdict". `_anthropic_api.py:289-292` keeps
only `text` blocks and discards `stop_reason`.

### Q6 Future-fit

Yes. Stop reasons are part of the Messages API contract. New reasons map to
a fixed category set, so a new value degrades to `incomplete`, not to a
scored answer.

## Step 0.5 Prior Art

Three searches: `git grep stop_reason -- scripts/eval` (no hit outside
provider adapters), the `.serena/memories` index for "stop_reason" (no hit),
and REQ-036 (names #5902 as the tracking issue). No prior design exists.

## Problem Statement

The eval adapter returns text only. A refusal or a token-limit cut-off is
scored as an ordinary model answer.

## User Stories

- As an eval operator, I read the termination category of each response in
  the eval output.
- As a gate owner, I see a refusal or a truncation fail as an error, never
  as a wrong or right verdict.
- As an evaluator author, I pass a task-specific `max_tokens` and it reaches
  the request.

## Ontology

- **Message response**: the structured result of one Messages API call.
- **Termination**: one of `completed`, `refusal`, `token_limit`,
  `incomplete`, `unknown`.
- **Refusal details**: `category` and `explanation` from `stop_details`,
  present only when the stop reason is `refusal`.
- **Text view**: the text blocks joined by a newline, as `call_api` returns
  today.

## Data Model

`MessageResponse`, a frozen dataclass: `text`, `stop_reason`,
`refusal_category`, `refusal_explanation`, `block_types`, `termination`.
It is created once per call and never mutated.

Termination map:

| `stop_reason` | Termination |
|---|---|
| `end_turn`, `stop_sequence` | `completed` |
| `refusal` | `refusal` |
| `max_tokens`, `model_context_window_exceeded` | `token_limit` |
| any other string | `incomplete` |
| missing or not a string | `unknown` |

A non-default provider returns text with no stop metadata, so its
termination is `unknown`.

## Integrations

Anthropic Messages API, non-streaming, `anthropic-version: 2023-06-01`.
`max_tokens` caps thinking and text together.

## Failure Modes

- The API adds a stop reason: it maps to `incomplete`, which is not scored
  as a completed answer.
- `stop_details` is null or has the wrong shape: refusal details are `None`
  and the termination is still `refusal`.
- A response holds only thinking blocks and stops on `max_tokens`: the text
  view is empty and the termination is `token_limit`.

## Security

No new surface. Refusal explanations come from the provider. They are
recorded in eval output, not in error messages, so the redaction rules for
exceptions do not change.

## Observability

The adapter log record and each migrated evaluator's output carry the
termination field.

## Acceptance Criteria

1. When the response has `stop_reason` `end_turn`, the adapter shall return
   termination `completed` and the joined text.
2. When the response has `stop_reason` `refusal`, the adapter shall return
   termination `refusal` with the `stop_details` category and explanation.
3. When the response has `stop_reason` `max_tokens`, the adapter shall
   return termination `token_limit`.
4. When the content mixes `thinking` and `text` blocks, the adapter shall
   return every block type in order and join only the text blocks.
5. `call_api` shall return the same text as before for every response shape.
6. When a caller passes a `metadata` dict, `call_api` shall write the
   termination and stop reason into it.
7. When a caller passes `max_tokens`, the request body shall carry that
   value.
8. `AnthropicAPIAdapter` shall accept a per-evaluation `max_tokens` and pass
   it to its transport.
9. When a response ends in `refusal`, `token_limit`, or `incomplete`, the
   adapter harness, the rule-activation judge, and the prompt-change
   evaluator shall record the termination and shall not score the response
   as an answer. The prompt-change evaluator shall exclude such runs from
   its scored-run count rather than counting them as a failed run.
10. The adapter shall add no streaming loop and no continuation request.
11. When a scenario has fewer scored runs than the run minimum, the
    prompt-change gate shall fail as inconclusive.

## Out of Scope

- Raising any default or per-evaluator `max_tokens`.
- Streaming, `pause_turn` continuation, or refusal fallbacks.
- Termination handling in evaluators that do not route metadata today and
  do not feed a gate.
- Stop metadata from non-default providers.

## Deferred

None.

## Open Questions

None.

## CVA Summary

Common: every call yields text. Varies: why generation stopped.
Relationship: the grader must see the reason before it scores the text.

## Buy-vs-build Decision

N/A (bug fix / doc / refactor)

## Complexity Classification

Tier 2. Domain: Clear. Methodology: parse the envelope, map the reason,
test each shape.
