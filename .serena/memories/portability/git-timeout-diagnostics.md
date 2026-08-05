# Git timeout diagnostics in portability validators

## Decision

Use `git_timeout_problem(proc, action)` at every fail-closed Git call site that needs operator-facing diagnostics.

## Reason

`run_git` returns code 124 on timeout. Generic `returncode != 0` checks still fail closed, but they hide which Git probe timed out. This makes CI failures hard to diagnose.

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
