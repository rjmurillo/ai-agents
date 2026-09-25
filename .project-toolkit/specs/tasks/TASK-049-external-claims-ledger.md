---
type: task
id: TASK-049
title: Gate research writes on a validated external claims ledger
status: implemented
priority: P1
related:
  - REQ-040
  - DESIGN-038
created: 2026-09-25
updated: 2026-09-25
author: plan
tags:
  - skills
  - research
  - routing
---

# TASK-049: Gate research writes on a validated external claims ledger

## Milestones

1. **Tests.** Write `tests/skills/ai-agents-external-claims/test_claim_ledger.py`
   first. It fails because the script does not exist.
2. **Validator.** Write
   `.claude/skills/ai-agents-external-claims/scripts/claim_ledger.py` until
   the tests pass.
3. **Adjunct.** Add the ledger contract and the adjunct mode to the
   `ai-agents-external-claims` template. Change its routing block.
4. **Gate.** Add the claim gate to the `research` template and to its
   verification list. Name it in the `autoplan` research row.
5. **Scenarios.** Add activation and skip scenarios to
   `tests/evals/skill-scenarios/research.json`.
6. **Render and prove.** Run `build_all.py`, the targeted tests, the
   routing-role gate, ruff, mypy, and `pre_pr.py`.

## Risks

| Risk | Mitigation |
|---|---|
| The model skips the gate | The gate is a numbered phase with a blocking exit code |
| The ledger drifts from the artifact | Rule 11 checks the artifact text |
| No network in the run | Source kind `none` with a recorded gap passes |
| Mirror drift | `build_all.py --check` |

## Done When

Every REQ-040 criterion maps to a passing test or a gate run.
