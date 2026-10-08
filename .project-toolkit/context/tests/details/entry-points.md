## Entry points

- `git_hook_policy.py pytest`: lefthook pre-push pytest command.
- `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`: the 4 local partitions (`_pytest_commands`); CI runs 6 legs (`scripts/ci/run_pytest_partition.py --partition`), local bulk covering CI `bulk`, `bulk-nested` and `bulk-nested-ci`.
- `check_zero_collection_tests.py`: finds a `test_*.py` under `testpaths` collecting zero tests.
