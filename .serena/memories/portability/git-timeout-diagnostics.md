# Git timeout diagnostics in portability validators

## Decision

Use `git_timeout_problem(proc, action)` at every fail-closed Git call site that needs operator-facing diagnostics.

## Reason

`run_git` returns code 124 on timeout. Generic `returncode != 0` checks still fail closed, but they hide which Git probe timed out. This makes CI failures hard to diagnose.

The 30-second bound is a hang ceiling, not a latency target. On 2026-08-05,
20 runs of every bounded probe in this repository covered 169,611 Git objects.
The slowest command was object enumeration at 179.915 ms maximum and
155.260 ms median. The next-slowest maximum was 22.681 ms. The bound was
therefore more than 166 times the slowest observed result.

One fixed bound keeps local and CI behavior deterministic. An environment
override would let the same commit pass locally and fail in CI. Per-operation
budgets add policy without an observed need. Retries would multiply a local
resource stall and delay the same fail-closed result.

## Failure mode

A larger repository or degraded disk can make a legitimate Git probe exceed
30 seconds. The validator will refuse the change and name the timed-out
operation. Reproduce that operation in the affected repository before changing
`GIT_TIMEOUT_SECONDS`. Increase the shared ceiling only when the measured
legitimate runtime needs it.

## Pattern

1. Call `run_git`.
2. Call `git_timeout_problem` with the exact operation.
3. Print or return the operation-specific problem.
4. Keep the existing generic nonzero fallback for other Git failures.

## Evidence

The follow-up to PR #4568 applied this pattern to tree listing, ref listing, object enumeration, repository-root lookup, HEAD lookup, baseline attributes, shared Git-line reads, history lookup, and committed-object reads. The focused portability selection passed 204 tests. The full suite passed 23,320 tests with 33 skips. Ruff and targeted mypy passed. Final observability review found no Critical or High issue.

## Files

- `scripts/validation/portability_git.py`
- `scripts/validation/portability_baseline.py`
- `scripts/validation/portability_common.py`
