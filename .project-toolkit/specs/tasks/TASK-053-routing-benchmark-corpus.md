---
type: task
id: TASK-053
title: Build the routing benchmark corpus, loader, and grader
status: implemented
priority: P1
related:
  - REQ-044
  - DESIGN-042
created: 2026-09-29
updated: 2026-09-29
author: plan
tags:
  - eval
  - routing-benchmark
---

# TASK-053: Build the routing benchmark corpus, loader, and grader

## Milestones

1. **Loader.** Strict parser, category and id checks, model-name scan, leak check.
2. **Grader.** Materialize, changed-path diff, scope check, hidden overlay, command run.
3. **Scenarios.** Six scenarios with known-good and known-bad controls.
4. **Controls and CLI.** `verify_controls` and `eval_routing_corpus.py` with exit codes.
5. **Tests.** Negative tests per loader rule and per grader rule.

## Dependencies

Milestones run in order. The #5424 runner consumes milestone 1 after merge.

## Risks

| Risk | Mitigation |
|---|---|
| A control passes for the wrong reason | Mutation sweep with an inverted control |
| Fixture code trips linters | The `.fixture` suffix |
| Answer key visible to a driver | Leak check and a separate `hidden/` tree |

## Done

Every REQ-044 criterion marked MET has a passing test.
