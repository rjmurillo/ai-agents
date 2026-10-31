# A cancelled pytest leg freezes the durations cache and repeats the timeout

## Observation

On 2026-10-21 `pytest (split-1)` hit its 10 minute job timeout on every main run.
Issue #6828 tracked it. PR #6829 fixed it (merge 18de18bca4).
That fix caused a second failure. See the sequel below.

## Mechanism

1. pytest-split `duration_based_chunks` cuts the test pool into contiguous runs.
2. That put the three slowest `tests/ci/` scans in one leg.
3. The `test-durations` job saves a new durations map only when every leg passes.
4. A cancelled leg meant no new map, so the stale cache stayed frozen.
5. The next run used the same bad split and timed out again.

This is a self-perpetuating failure. Reruns cannot fix it.

## Sequel: least_duration scattered modules (issue #6846)

PR #6829 switched pytest-split to `least_duration`. It places single tests, not files.
By run 39886538175 (2026-10-23), 1835 of 1984 modules sat on more than one leg.
Before the switch, run 39414484184 had 3 of 1959 modules on more than one leg.
Tests that share a cached whole-repo scan reran that scan on every leg.
`test_guard_diff.py` scanned three times. `test_windows_path_filter_repo.py` went from 42.9s to 642.3s.
The slow-test budget gate and the leg wall-time gate went red on main.

PR #6853 split by whole module, longest module first, on the least loaded leg.
PR #6857 made each leg run its longest module first, so a long test cannot start late.
Both merged 2026-10-23.

## Rule

Split by whole module, never by single test. Never rerun a timed-out leg.
`scripts/ci/pytest_module_split.py` is the in-repo plugin. It takes `--module-splits` and `--module-group`.
`scripts/ci/run_pytest_partition.py` builds those flags in `split_flags()`. Five legs run.
pytest-split still records durations. It no longer picks the split.
Check module spread before changing the algorithm. Fix the split or the cache.

## Related: required check stuck in_progress

A required check can stay `in_progress` after its job succeeded (issue #6830).
`gh run rerun <run>` clears it. `gh run cancel` refuses because the run is already completed.
