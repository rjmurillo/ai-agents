---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-10035-b48c43aa7-ship-pytest-local-fallback-partitions.json
qaCommit: 8177af6e5fe85b78ef7fd79625cbb4284bf57f45
---

# QA Report: Issue 4854 ACT local fallback

## Result

PASS. When the workflow gate already runs inside act, it executes each pytest
matrix entry directly. Each entry gets the full 600-second timeout. Child
pytest processes do not inherit `ACT=true`.

## Evidence

- Focused rerun after merging current `origin/main`: 143 passed in 7.91
  seconds. This included the prior failing mutation signal case.
- `uv run ruff check scripts/validation/run_workflow_local_test.py
  tests/validation/test_run_workflow_local_test.py`: passed.
- `uv run --frozen python scripts/ci/taste_count_ratchet.py --base-ref
  origin/main`: 583, equal to baseline.
- `git diff --check`: passed.
- `test_act_true_runs_pytest_matrix_locally` covers two matrix entries,
  `-n auto --dist loadfile`, the timeout, working directory, bytecode guard,
  and removal of `ACT` from child environments.

## Scope

This slice changes the local workflow runner only. The stacked partition PR
owns `pytest.yml`, coverage aggregation, and CI duration evidence.
