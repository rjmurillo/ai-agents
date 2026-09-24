---
type: requirement
id: REQ-035
title: Grade orchestrator S2 and S5 on the decision, and move the eval default to Sonnet 5
status: implemented
priority: P2
category: functional
source: PR-5904
related:
  - DESIGN-033
  - TASK-044
created: 2026-09-24
updated: 2026-09-24
author: spec
tags:
  - eval
  - orchestrator
  - model-routing
---

# REQ-035: Grade orchestrator S2 and S5 on the decision, and move the eval default to Sonnet 5

## Step 0 First Principles

### Q1 Demand Reality

rjmurillo, the repository owner, set a session goal on 2026-09-24 to fix the
two problems PR #5904 recorded as residual: orchestrator S2 and S5 failing,
and the prompt-change evaluator defaulting to `claude-sonnet-4-6`.

### Q2 Status Quo

Every orchestrator prompt change runs the scenario corpus. S2 and S5 fail on
every run, so the acceptance gate reports FAIL or an unexplained regression
for a prompt change that did not touch them. Reviewers learn to ignore it.

### Q3 Desperate Specificity

The orchestrator prompt-change gate. PR #5904's ablation run reported
`no_unexplained_regressions: FAIL` because of S2.

### Q4 Narrowest Wedge

About 1 hour: drop the synonym label from S2 and S5, bump one constant, add
one pricing row, and rerun the corpus.

### Q5 Observation

PR #5904 ablation on `claude-sonnet-4-6`: S2 went from 3 of 3 to 0 of 3, and
S5 failed on both arms. A 2026-09-24 baseline on `claude-sonnet-5` with the
current prompt answered DELEGATE on S2 in 5 of 6 runs and on S5 in 6 of 6, with
reasons "route to analyst first for investigation" and "delegate to the
security agent". Those are the intended behaviors under a different label.

### Q6 Future-fit

Yes. Fewer synonym labels make each scenario test one decision. The single
default constant keeps a future model bump to one line.

## Step 0.5 Prior Art

PR #5904 fixed the same synonym defect in S11. `_anthropic_api.py` states the
constant is the single source of truth for the eval default (issue #2858).

## Problem Statement

S2 and S5 offer both ROUTE and DELEGATE. The model takes the intended action
and names it DELEGATE, so the scenarios fail on wording. The prompt-change
evaluator defaults to a model the routing policy no longer names.

## User Stories

- As a prompt author, I see S2 and S5 pass when the orchestrator routes to the
  right specialist.
- As an eval operator, I get the routing policy's model when I pass no
  `--model`.

## Ontology

- **Scenario**: one entry in `tests/evals/orchestrator-scenarios.json`.
- **Verdict label**: one entry of a scenario's `verdict_options`.
- **Default model**: `DEFAULT_MODEL` in `scripts/eval/_anthropic_api.py`.

## Data Model

No schema change. Two scenarios lose one verdict label. One pricing row is
added.

## Integrations

Anthropic Messages API. `claude-sonnet-5` rejects `temperature`; the existing
fallback in `call_api` retries without it.

## Failure Modes

- The default has no pricing row: cost estimation raises. A test guards it.
- A scenario loses its only discriminating label: the reason check on S2
  (`investigat`) and S5 (`security`) still separates the right specialist
  from the wrong one, and EXECUTE and ASK remain wrong answers.

## Security

No security surface.

## Observability

The prompt-change report records the model and every per-run verdict.

## Acceptance Criteria

1. The S1 to S5 scenarios shall not offer DELEGATE beside ROUTE.
2. The S2 and S5 scenarios shall keep their expected verdict and reason check.
   The S2 check shall match both "investigate" and "investigation".
3. `DEFAULT_MODEL` shall be `claude-sonnet-5`.
4. The pricing table shall carry a `claude-sonnet-5` row at $2 and $10 per
   million tokens.
5. The S10 scenario shall grade its STOP verdict without a phrase check.
6. A live prompt-change run of the orchestrator corpus with no `--model`
   shall use `claude-sonnet-5` and pass S2, S5, and S10 in at least two of
   three runs per arm.

## Out of Scope

- Evaluators that hard-code their own default model.
- Orchestrator prompt edits.
- Reason checks on scenarios that pass the two-of-three rule (S8, S9, S13).

## Deferred

None.

## Open Questions

None.

## CVA Summary

Common: every orchestrator scenario grades one decision through one label.
Varies: which label names it. Relationship: two labels that mean the same
action split the vote.

## Buy-vs-build Decision

N/A (bug fix / doc / refactor)

## Complexity Classification

Tier 1. Domain: Clear. Methodology: fix, then rerun the corpus.
