# A cancelled pytest leg freezes the durations cache and repeats the timeout

## Observation

On 2026-10-21 `pytest (split-1)` hit its 10 minute job timeout on every main run.
Issue #6828 tracked it. PR #6829 fixed it (merge 18de18bca4).

## Mechanism

1. pytest-split `duration_based_chunks` cuts the test pool into contiguous runs.
2. That put the three slowest `tests/ci/` scans in one leg.
3. The `test-durations` job saves a new durations map only when every leg passes.
4. A cancelled leg meant no new map, so the stale cache stayed frozen.
5. The next run used the same bad split and timed out again.

This is a self-perpetuating failure. Reruns cannot fix it.

## Rule

Fix the split or the cache. Never rerun. PR #6829 switched the legs to `least_duration`.

## Related: required check stuck in_progress

A required check can stay `in_progress` after its job succeeded (issue #6830).
`gh run rerun <run>` clears it. `gh run cancel` refuses because the run is already completed.
