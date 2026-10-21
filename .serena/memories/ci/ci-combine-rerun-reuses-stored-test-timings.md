# Re-running the Combine Job Reuses Stored Test Timings

## The contradiction

The usual fix for a flaky timing gate is "re-run the failed job". Here that
does not work for the slow-test budget.

`.github/workflows/pytest.yml:560` (`Combine Python coverage`) downloads the
JUnit XML artifacts that the `pytest (split-N)` legs uploaded. Then
`scripts/testing/slow_test_budget.py` sums seconds per module from those files
(`pytest.yml:619-632`). The combine job runs no tests itself.

`gh run rerun --failed` re-runs only the combine job when it is the only red
job. It reads the same stored XML and reports the same numbers.

## Evidence

- PR #6754 (2026-10-19): a re-run failed with the identical 49.99s against
  the 40.00s budget.
- PR #6800 run 39403219573 (2026-10-20): a combine-only re-run reproduced
  53.19s. Re-running the `pytest (split-5)` leg made the run pass (issue #6802,
  closed as a duplicate of #6757).

## What to do

- Re-run the test leg that recorded the slow module, not the combine job.
- Or push a new commit, such as a merge of main, to force a full run.
- Never raise the budget to clear a single noisy sample. Budget changes are
  owner decisions (issue #6757).
