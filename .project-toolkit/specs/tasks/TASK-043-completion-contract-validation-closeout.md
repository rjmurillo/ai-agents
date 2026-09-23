---
type: task
id: TASK-043
title: Close the completion-contract validation gaps
status: todo
priority: P1
complexity: M
related:
  - REQ-034
  - DESIGN-032
created: 2026-09-23
updated: 2026-09-23
author: plan
tags:
  - eval
  - runtime-parity
---

# TASK-043: Close the completion-contract validation gaps

Implements REQ-034 per DESIGN-032. One PR against #5404.

## Milestones

1. Capture baselines: runtime corpus on main, verdict ablation against
   `2e78453a8` for the orchestrator, critic, and QA corpora.
2. Copilot install path, listing preflight, and argv change in
   `scripts/eval/_runtime_harness.py` and `scripts/eval/eval_runtime_parity.py`,
   test-first.
3. Scenario 13 assertion change in
   `tests/evals/completion-terminal-runtime-fixtures.json`.
4. README threshold and Copilot contract in `scripts/eval/README.md`.
5. Candidate runs: at least three per arm, Claude harness; Copilot run
   recorded with its real exit code.

## Risks

- Copilot model quota stays exhausted. The run reports exit 3 and the PR
  says so. No behavior claim for Copilot.
- The listing format changes in a later CLI. The preflight fails closed
  with exit 2 or 3.

## Done When

REQ-034 criteria 1 to 10 each have a passing test or a recorded run.
