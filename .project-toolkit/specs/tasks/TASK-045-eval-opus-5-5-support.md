---
type: task
id: TASK-045
title: Run the eval harness on Claude Opus 5.5
status: done
priority: P2
complexity: S
related:
  - REQ-036
  - DESIGN-034
created: 2026-09-24
updated: 2026-09-24
author: plan
tags:
  - eval
  - orchestrator
---

# TASK-045: Run the eval harness on Claude Opus 5.5

Implements REQ-036 per DESIGN-034. One PR.

## Steps

1. Baseline the orchestrator corpus on `claude-opus-5-5`.
2. Add the two pricing rows and the panel tier.
3. Drop the S8, S9, and S13 phrase checks.
4. Add the two pricing tests and check each fails on a skewed dotted rate.
5. Rerun the corpus on `claude-opus-5-5` and with no `--model`.

## Done When

REQ-036 criteria 1 to 6 each have a passing test or a recorded run.
