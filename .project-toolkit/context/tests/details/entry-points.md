## Entry points

- `git_hook_policy.py pytest`: lefthook pre-push pytest command.
- `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`: the 4 local partitions (`_pytest_commands`); CI runs 6 legs (`scripts/ci/run_pytest_partition.py --partition`): `split-1` to `split-4` (pytest-split, balanced by `tests/.test_durations`), `safe-push`, `pr-autofix`. `split-1` is the `primary` leg that carries the once-per-run steps.
- `check_zero_collection_tests.py`: finds a `test_*.py` under `testpaths` collecting zero tests.
- Refresh `tests/.test_durations` (a stale file only skews the split, it never drops a test; `tests/ci/test_pytest_split_pool.py` fails when over 20% of the pool is missing from it). Run the whole pool once, with no `--splits`, from the repo root:
  `uv run python -m pytest -n auto --dist loadfile --store-durations --clean-durations --durations-path tests/.test_durations $(uv run python -c "from scripts.ci import run_pytest_partition as r; print(' '.join(r._POOL_IGNORES))") tests/`
