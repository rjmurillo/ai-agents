## Entry points

- `git_hook_policy.py pytest`: lefthook pre-push pytest command.
- `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`: the 4 local partitions (`_pytest_commands`); CI runs 6 legs (`run_pytest_partition.py`): `split-1`..`4`, `safe-push`, `pr-autofix`.
- `check_zero_collection_tests.py`: finds a `test_*.py` under `testpaths` collecting zero tests.
- Refresh `tests/.test_durations`: see `SPLIT_COUNT` in `run_pytest_partition.py`. Over 20% missing fails `test_pytest_split_pool.py`.
