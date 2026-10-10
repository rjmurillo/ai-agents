## Entry points

- `git_hook_policy.py pytest`: lefthook pre-push pytest command.
- `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`: the 4 local partitions; CI runs 6 legs: `split-1`..`4`, `safe-push`, `pr-autofix`.
- `check_zero_collection_tests.py`: finds a `test_*.py` under `testpaths` collecting zero tests.
- One leg: `uv run python scripts/ci/run_pytest_partition.py --partition split-1`. Timings come from the Actions cache (`pytest-split-durations-`), saved on pushes to main; without it legs split by test count. `duration_gate_check.py` (coverage job) fails a leg over 480 s and warns at a 1.5x split spread.
