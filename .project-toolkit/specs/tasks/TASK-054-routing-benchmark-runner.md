---
type: task
id: TASK-054
title: Build the routing benchmark runner
status: implemented
priority: P1
related:
  - REQ-045
  - DESIGN-043
created: 2026-09-29
updated: 2026-09-29
author: plan
tags:
  - eval
  - routing-benchmark
---

# TASK-054: Build the routing benchmark runner

## Milestones

1. **Config.** Parser and A-F invariants, including C and D held constant against A.
2. **Plan.** Matrix eligibility, model and effort checks, matched-pair classification.
3. **Results and DAG.** Records, verdicts, cost from in-tree rates, invocation shapes.
4. **Fake runner.** Scripted backend, violation detection, pair comparison.
5. **Live gate.** Credential gate and a backend tested with a fake process runner.
6. **CLI and docs.** Exit codes, example config, README section.

## Dependencies

The corpus loader from TASK-053 feeds milestones 2 and 4. Milestones run in order.

## Risks

| Risk | Mitigation |
|---|---|
| A guard passes for the wrong reason | Mutation sweep with an inverted control |
| The live path is unrun | Gate tested, backend tested with a fake runner, status stated in the PR |
| Matrix flips make a test brittle | Tests use synthetic matrices, not the checked-in one |

## Done

Every REQ-045 criterion marked MET has a passing test.
