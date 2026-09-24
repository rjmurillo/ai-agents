---
type: requirement
id: REQ-036
title: Run the eval harness on Claude Opus 5.5
status: implemented
priority: P2
category: functional
source: session-goal-2026-09-24
related:
  - DESIGN-034
  - TASK-045
created: 2026-09-24
updated: 2026-09-24
author: spec
tags:
  - eval
  - orchestrator
  - model-routing
---

# REQ-036: Run the eval harness on Claude Opus 5.5

## Step 0 First Principles

### Q1 Demand Reality

rjmurillo, the repository owner, asked on 2026-09-24 for the evals to also
test Opus 5.5. The routing policy in `AGENTS.md` names Opus 5.5 as the default
frontier model.

### Q2 Status Quo

An operator can pass `--model claude-opus-5-5` to the Anthropic path. Cost
estimation has no rate for that id, so a priced run fails closed. The owner
model panel runs Opus 5 and GPT-5.6 Sol, not Opus 5.5.

### Q3 Desperate Specificity

`scripts/eval/panels/owner-copilot-cli.json` and the orchestrator
prompt-change corpus. A 2026-09-24 baseline of that corpus on
`claude-opus-5-5` reported `no_high_flakiness: FAIL` and blocked S13.

### Q4 Narrowest Wedge

About 1 hour: two pricing rows, one panel tier, three phrase checks removed,
two tests, and live corpus runs.

### Q5 Observation

2026-09-24 baseline on `claude-opus-5-5`, 14 scenarios, 3 runs per arm:
84 of 84 verdicts matched the expected label and 84 of 84 responses parsed.
The gate still failed. S8, S9, and S13 answered STOP in 6 of 6 runs each, but
some reasons omitted the phrase `terminal` or `side quest`.

### Q6 Future-fit

Yes. Grading the decision instead of wording holds across models. The
spelling-consistency test catches a future dotted and dashed rate pair that
disagree.

## Step 0.5 Prior Art

PR #5908 added the `claude-sonnet-5` rate and removed the S10 phrase check for
the same wording defect. `scripts/eval/_runtime_output.py` records that
Copilot CLI accepts only `claude-opus-5.5` and Claude Code only
`claude-opus-5-5`. `call_with_temperature_fallback` already retries without
`temperature`, which Opus 5.5 rejects.

## Problem Statement

The harness cannot price an Opus 5.5 run, the owner panel does not include
Opus 5.5, and the orchestrator corpus fails Opus 5.5 on wording while its
decisions are correct.

## User Stories

- As an eval operator, I run any Anthropic eval with
  `--model claude-opus-5-5` and get a cost estimate.
- As the owner, I run the owner panel and get an Opus 5.5 column.
- As a prompt author, I see the orchestrator gate grade Opus 5.5 on its
  decisions.

## Ontology

- **Pricing row**: one key of `MODEL_PRICING_RATES_USD_PER_1K_TOKENS` in
  `scripts/eval/_eval_common.py`.
- **Panel tier**: one entry of `tiers` in a file under `scripts/eval/panels/`.
- **Phrase check**: the `expected_reason_contains` field of a scenario.

## Data Model

No schema change. Two pricing rows, one panel tier, and three removed
`expected_reason_contains` fields.

## Integrations

Anthropic Messages API for `claude-opus-5-5`. Copilot CLI for the panel tier
`claude-opus-5.5`.

## Failure Modes

- A spelling has no rate: the child evaluator exits 2 on an unpriced id.
  `test_shipped_panel_anthropic_models_are_priced` guards the panel id, and
  `test_opus_5_5_is_priced_in_both_harness_spellings` guards both.
- The two spellings drift to different rates: one model reports two costs.
  `test_spellings_of_one_model_share_one_rate` guards every pair.
- Opus 5.5 thinking cannot be disabled and may use the 1,024-token budget:
  the answer truncates. The 2026-09-24 baseline parsed 84 of 84 responses, so
  no budget change is made.

## Security

No security surface. The API key comes from the environment or the operator
vault and is never written to a file.

## Observability

The prompt-change report records the model and every per-run verdict.

## Acceptance Criteria

1. The pricing table shall carry `claude-opus-5-5` and `claude-opus-5.5` at
   $4 input and $20 output per million tokens.
2. Every pair of pricing rows that names one model in two spellings shall
   carry one rate.
3. The owner panel shall dispatch `claude-opus-5.5` on `copilot-cli` as a
   reference tier.
4. Orchestrator S8, S9, and S13 shall grade STOP without a phrase check.
5. A live prompt-change run of the orchestrator corpus on `claude-opus-5-5`
   shall pass the acceptance gate.
6. A live prompt-change run of the orchestrator corpus with no `--model` shall
   pass the acceptance gate.

## Out of Scope

- Changing `DEFAULT_MODEL`.
- Raising `max_tokens` in any evaluator.
- A live run of the Copilot CLI panel, which spends Copilot quota.
- Phrase checks in other scenario corpora.

## Deferred

None.

## Open Questions

None.

## CVA Summary

Common: every eval prices a model id and grades one decision per scenario.
Varies: the id spelling per harness and the words a model uses. Relationship:
a price keyed on one spelling, or a grade keyed on one word, fails a correct
run.

## Buy-vs-build Decision

N/A (bug fix / doc / refactor)

## Complexity Classification

Tier 1. Domain: Clear. Methodology: add rows, rerun the corpus.
