---
type: requirement
id: REQ-045
title: Configurable multi-arm routing benchmark runner with a zero-spend dry run
status: implemented
priority: P1
category: functional
source: issue-5424
related:
  - DESIGN-043
  - TASK-054
  - REQ-044
  - REQ-042
created: 2026-09-29
updated: 2026-09-29
author: spec
tags:
  - eval
  - routing-benchmark
---

# REQ-045: Configurable multi-arm routing benchmark runner with a zero-spend dry run

## Step 0 First Principles

### Q1 Demand Reality

Issue #5424 is child 2 of tracker #5422. The experiment compares six strategy
arms across Codex and Copilot. It needs a runner before any paid comparison.

### Q2 Status Quo

The #5423 capability matrix and probes are on `main`. No file in `scripts/eval`
expands strategy x scenario x harness, reads the matrix's eligibility classes,
or defines a result record with harness identity.

### Q3 Desperate Specificity

The owner needs to see, before spend, which combinations are eligible, which
are unmatched, and which are rejected. Issue #5426 needs the runner to execute.

### Q4 Narrowest Wedge

One config format, one zero-spend plan, one deterministic fake backend, one
gated live backend, one CLI. The fake backend grades with the #5425 corpus.

### Q5 Observation

Measured on `main` at `1e435978f` on 2026-09-29: `build_report` in
`scripts/eval/_harness_capability.py` reads UNVERIFIED for every arm on both
harnesses, so the checked-in matrix plans nothing today.

### Q6 Future-fit

The result record is the input to #5426. The live backend gains backend
evidence readers when the probes' parsers are wired in.

## Owner decision

The owner chose on 2026-09-29 to build the offline parts of #5424 and #5425
now, although #5424 says it is blocked by #5423. Paid live runs stay out of
scope. The live path is wired, gated, and unrun.

## Acceptance criteria

Status column: MET means a test proves it. PARTIAL and OPEN stay open on the
issue.

| ID | Criterion | Status |
|---|---|---|
| AC-1 | The #5423 matrix is consumed directly through `load_matrix` and `build_report`. | MET |
| AC-2 | Codex and Copilot are config dimensions and appear in every result. | MET |
| AC-3 | Arms A to F are expressible from config, with their invariants enforced. | MET |
| AC-4 | A matched harness comparison needs equal semantic contracts. | MET |
| AC-5 | A material difference yields UNMATCHED with the field named. | MET |
| AC-6 | Harness name and version are persisted in every result. | MET |
| AC-7 | Requested and observed model and effort are kept per invocation. | MET |
| AC-8 | Tool sandbox, concurrency, context, telemetry, and reviewer isolation differences are recorded. | MET |
| AC-9 | Harness retry semantics are recorded per run. | PARTIAL |
| AC-10 | The dry run expands the exact plan with zero model calls. | MET |
| AC-11 | Tests cover matched, unmatched, unsupported, and harness-failure cases. | MET |
| AC-12 | Pricing, auth allowlists, and flag shapes reuse in-tree code. | MET |
| AC-13 | The live path is gated by `--live` plus credentials and fails closed. | MET |
| AC-14 | Live runs read backend evidence for observed model and effort. | OPEN |
| AC-15 | A paid comparison runs and reports. | OPEN |

AC-9: a run records correction rounds and harness failures. Harness-level
retry behavior stays in the matrix `failure_retry_behavior` field.

## Out of scope

Paid comparisons, choosing a winner, editing routing defaults, new harness
support, and any change to `task-decomposer`.
