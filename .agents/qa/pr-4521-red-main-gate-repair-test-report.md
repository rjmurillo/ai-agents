---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-03-session-9014.json
qaCommit: 67c1ac9b227af70ccfcfd0ae92ef8a2802eae6c0
---
# PR 4521 Red Main Gate Repair Test Report

## Scope

PR 4521 repairs CI gates that were failing on main and then merges the current main branch to pick up the lowered memory-index baseline. The user impact is a pushable branch with the required PR validation gate no longer blocked by stale ratchet state.

## Verification

| Check | Result | Evidence |
|---|---:|---|
| PR description validation | PASS | `uv run --frozen python scripts/validation/pr_description.py --pr-number 4521 --ci` reported that the PR description matches the diff. |
| Memory index validation | PASS | `memory_index.py`, `memory_index_count_ratchet.py --base-ref origin/main`, and `memory_index_token_ratchet.py` passed. |
| Generated artifacts | PASS | `uv run --frozen python build/scripts/build_all.py --check` completed after regenerating expected surfaces in the worktree. |
| Focused tests | PASS | `uv run --frozen pytest tests/ci/test_pr_validation_workflow.py tests/ci/test_write_copilot_synthesis_summary.py -q` collected 75 items and passed 75. |
| Pre-push suite progress | PASS before QA gate | Pre-push reached `24,881 passed, 34 skipped, 50 deselected` before `pre_pr` stopped on this missing QA evidence. |

## Risk Review

- The remaining change after validation is QA evidence only.
- The merge resolves stale main baseline drift instead of raising any baseline.
- Conflict markers and duplicate memory-index rows were checked after resolution.
