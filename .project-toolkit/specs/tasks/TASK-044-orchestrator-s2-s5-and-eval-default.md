---
type: task
id: TASK-044
title: Grade orchestrator S2 and S5 on the decision, and move the eval default to Sonnet 5
status: done
priority: P2
complexity: S
related:
  - REQ-035
  - DESIGN-033
created: 2026-09-24
updated: 2026-09-24
author: plan
tags:
  - eval
  - orchestrator
---

# TASK-044: Grade orchestrator S2 and S5 on the decision, and move the eval default to Sonnet 5

Implements REQ-035 per DESIGN-033. One PR.

## Steps

1. Baseline the orchestrator corpus on `claude-sonnet-5` with the current
   scenarios.
2. Drop DELEGATE from S1 to S5. Stem the S2 reason check. Drop the S10
   phrase check.
3. Bump `DEFAULT_MODEL` and add the pricing row; update the default test.
4. Rerun the corpus with no `--model`.

## Done When

REQ-035 criteria 1 to 6 each have a passing test or a recorded run.
