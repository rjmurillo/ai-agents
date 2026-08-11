---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-10035-b48c43aa7-ship-pytest-local-fallback-partitions.json
qaCommit: 0479e20938edb419d53443cd72097b826f334d4d
---

# QA Report: PR 4872 local pytest loop

## Result

PASS. When the workflow gate already runs inside act, it skips every `gh act`
call and executes each pytest matrix entry directly. Each entry gets the full
600-second timeout. Child pytest processes do not inherit `ACT=true`.

The shared pre-push gate now uses four workload partitions. Bulk and mutation
use `-n auto --dist loadfile`. Push-safety and pr-autofix modules stay serial.

## Evidence

- Final fallback file: 141 passed in 5.83 seconds.
- `uv run ruff check scripts/validation/run_workflow_local_test.py
  tests/validation/test_run_workflow_local_test.py`: passed.
- `uv run --frozen python scripts/ci/taste_count_ratchet.py --base-ref
  origin/main`: 583, equal to baseline.
- `git diff --check`: passed.
- `test_act_true_runs_pytest_matrix_locally` covers two matrix entries,
  `-n auto --dist loadfile`, the timeout, working directory, bytecode guard,
  removal of `ACT` from child environments, and absence of any `gh act`
  dry-run call.
- Child workers receive checkout-local `COPILOT_PLUGIN_ROOT` and
  `CLAUDE_PLUGIN_ROOT` values.
- Real pre-push pytest gate: 325.73 seconds total.
  - Bulk: 26,920 passed, 36 skipped in 188.65 seconds.
  - Mutation: 20 passed in 119.85 seconds.
  - Push safety: 46 passed, 9 deselected in 8.65 seconds.
  - PR autofix: 24 passed in 2.63 seconds.
- Security agent review: PASS. Commands use explicit argument arrays,
  validated worker input, complete test coverage, and fail closed.

## Scope

The stacked partition PR owns `pytest.yml`, coverage aggregation, and live CI
duration evidence.
