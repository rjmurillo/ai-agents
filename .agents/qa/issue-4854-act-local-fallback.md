---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-10035-b48c43aa7-ship-pytest-local-fallback-partitions.json
qaCommit: a004eec5f3790649436219daaa0ddb79a9fa0947
---

# QA Report: Issue 4854 ACT local fallback

## Result

PASS. When the workflow gate already runs inside act, it executes each pytest
matrix entry directly. Each entry gets the full 600-second timeout. Child
pytest processes do not inherit `ACT=true`.

## Evidence

- `uv run pytest tests/validation/test_run_workflow_local_test.py -q`: 141
  passed in 5.84 seconds.
- `uv run ruff check scripts/validation/run_workflow_local_test.py
  tests/validation/test_run_workflow_local_test.py`: passed.
- `git diff --check`: passed.
- `test_act_true_runs_pytest_matrix_locally` covers two matrix entries,
  `-n auto --dist loadfile`, the timeout, working directory, bytecode guard,
  and removal of `ACT` from child environments.

## Scope

This slice changes the local workflow runner only. The stacked partition PR
owns `pytest.yml`, coverage aggregation, and CI duration evidence.
