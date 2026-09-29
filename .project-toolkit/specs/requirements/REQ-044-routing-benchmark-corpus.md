---
type: requirement
id: REQ-044
title: Deterministic scenario corpus for the role-separated routing benchmark
status: implemented
priority: P1
category: functional
source: issue-5425
related:
  - DESIGN-042
  - TASK-053
  - REQ-042
created: 2026-09-29
updated: 2026-09-29
author: spec
tags:
  - eval
  - routing-benchmark
---

# REQ-044: Deterministic scenario corpus for the role-separated routing benchmark

## Step 0 First Principles

### Q1 Demand Reality

Issue #5425 is child 3 of tracker #5422. The routing experiment needs one
shared task set that every strategy arm receives unchanged.

### Q2 Status Quo

No scenario file, grader, or corpus validator for routing arms exists in
`scripts/eval` or `evals/`. Existing corpora are C# issue fixtures and prompt
fixtures. Neither is a runnable repository with a changed-path grader.

### Q3 Desperate Specificity

The #5424 runner needs scenario ids, categories, difficulty classes, and
allowed paths before it can plan a strategy by scenario matrix.

### Q4 Narrowest Wedge

Six scenarios, one per required category. One strict loader. One
deterministic grader. Known-good and known-bad controls for each scenario.

### Q5 Observation

Measured on `main` at `1e435978f` on 2026-09-29: no file under `scripts/eval`
or `evals` defines a scenario contract with allowed and forbidden paths.

### Q6 Future-fit

The loader is the input contract for #5424 and the later execution issue
#5426. A new category needs a code change, which is intended.

## Owner decision

The owner chose on 2026-09-29 to build the offline parts of #5424 and #5425
now, although #5425 says it is blocked by #5424. This change builds only the
corpus, the grader, and the validator. It runs no paid model.

## Acceptance criteria

Status column: MET means a test proves it. OPEN means it needs a paid run or
the #5424 runner and stays open on the issue.

| ID | Criterion | Status |
|---|---|---|
| AC-1 | The loader covers exactly six categories, one scenario each, and refuses a missing or repeated one. | MET |
| AC-2 | Each scenario has scope, invariants, criteria, commands, and reset. | MET |
| AC-3 | Scenarios name no model, and the loader refuses a model name. | MET |
| AC-4 | Grading is deterministic and a judge dimension cannot override it. | MET |
| AC-5 | Category 4 grades an unauthorized changed path as FAIL. | MET |
| AC-6 | Category 5 has a known-bad state that passes the visible check and fails grading with the expected finding. | MET |
| AC-7 | Category 6 stores the decision apart from the driver contract. | MET |
| AC-8 | Adapted scenarios cite an in-tree source and copy no fix. | MET |
| AC-9 | Validator tests cover missing categories, bad metadata, missing fixtures, duplicate ids, known-good PASS, and known-bad FAIL. | MET |
| AC-10 | The #5424 runner consumes the merged scenario contract. | OPEN |

## Out of scope

Paid model runs, prompt tuning, routing defaults, and any change to
`task-decomposer`.
