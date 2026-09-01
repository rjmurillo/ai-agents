# Retrospective: fix(completion-gate) require disposition evidence

## Session Info

- **Date**: 2026-08-15
- **Task Type**: Bug fix
- **Outcome**: Success

## What Happened

Issue #4902: the completion gate accepted PRs with failed non-required checks
without requiring any evidence that the failures were investigated. When the
base branch had zero required checks, `CIPassing=True` and
`MergeStateStatus='UNSTABLE'` passed the gate unconditionally.

## Root Cause

The `pass_when_python` expression in `pr-review-config.yaml` allowed `UNSTABLE`
without checking whether failed non-required checks had disposition evidence.
The `check_merge_readiness` function never blocked on non-required failures
unless `--include-non-required` was explicitly set.

## Fix

Added `_check_nonrequired_dispositions()` to `test_pr_merge_ready.py`:
- Reads a JSON dispositions file mapping check names to valid dispositions
- Undisposed failures add a blocking reason (CanMerge=False)
- Updated pass_when_python to verify `UndisposedNonRequiredFailures` is empty

## Lessons

1. Allowing `UNSTABLE` in a merge gate without evidence is equivalent to
   ignoring non-required check failures entirely
2. The disposition mechanism gives operators a structured way to acknowledge
   failures rather than silently passing
