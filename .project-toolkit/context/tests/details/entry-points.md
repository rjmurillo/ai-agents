## Entry points

- `git_hook_policy.py pytest`: lefthook pre-push pytest command.
- `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`: the 4 local partitions; CI runs 6 legs: `split-1`..`4`, `safe-push`, `pr-autofix`.
- `check_zero_collection_tests.py`: finds a `test_*.py` under `testpaths` collecting zero tests.
- One leg: `uv run python scripts/ci/run_pytest_partition.py --partition split-1`; refresh `tests/.test_durations` with `--refresh-durations` in place of `--partition`. Refresh at over 20% missing (`tests/ci/test_pytest_split_durations.py`) or a leg near the 10-minute limit.
