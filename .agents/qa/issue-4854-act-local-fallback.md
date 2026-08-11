---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-10035-b48c43aa7-ship-pytest-local-fallback-partitions.json
qaCommit: 5d2bed8edea08d65aa8ba14f8b192616c7119b5a
---

# QA Report: Issue 4854 ACT local fallback

## Result

PASS. When the workflow gate already runs inside act, it skips every `gh act`
call and executes each pytest matrix entry directly. Each entry gets the full
600-second timeout. Child pytest processes do not inherit `ACT=true`.

## Evidence

- Final fallback file: 141 passed in 5.82 seconds.
- `uv run ruff check scripts/validation/run_workflow_local_test.py
  tests/validation/test_run_workflow_local_test.py`: passed.
- `uv run --frozen python scripts/ci/taste_count_ratchet.py --base-ref
  origin/main`: 583, equal to baseline.
- `git diff --check`: passed.
- `test_act_true_runs_pytest_matrix_locally` covers two matrix entries,
  `-n auto --dist loadfile`, the timeout, working directory, bytecode guard,
  removal of `ACT` from child environments, and absence of any `gh act`
  dry-run call.

## Scope

This slice changes the local workflow runner only. The stacked partition PR
owns `pytest.yml`, coverage aggregation, and CI duration evidence.
