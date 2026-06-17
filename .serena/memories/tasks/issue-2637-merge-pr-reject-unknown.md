# Issue 2637: merge_pr rejects UNKNOWN merge state before direct merge

## Problem
`merge_pr.py` fetched PR state (state, mergeable, mergeStateStatus) but only
checked `state` for MERGED/CLOSED. It merged even when GitHub reported
mergeable=UNKNOWN / mergeStateStatus=UNKNOWN (mid-recalculation after a base
update), bypassing the readiness state that `test_pr_merge_ready.py` and
`run_completion_gate.py` enforce ("Merge status is being calculated"). Observed
on PRs #2632 and #2628 during pr-autofix: the completion gate rejected, merge_pr
merged anyway.

## Fix
Added `_reject_unknown_merge_state(pr_data, pr, output_format)` in
`merge_pr.py`. Called after the CLOSED check, gated on `not args.auto`. When
`mergeable == "UNKNOWN"` OR `mergeStateStatus == "UNKNOWN"`, it emits an error
envelope and exits with ADR-035 code 3 (external/transient), type `ApiError`.
`--auto` is exempt: auto-merge defers to GitHub's own gate.

## Canonical contract mirrored
`test_pr_merge_ready.py::_evaluate_pr_state` appends reason
"Merge status is being calculated" for `mergeable == "UNKNOWN"`.

## Files
- `.claude/skills/github/scripts/pr/merge_pr.py` (fix)
- `src/copilot-cli/skills/github/scripts/pr/merge_pr.py` (1:1 mirror, kept byte-identical)
- `tests/test_merge_pr.py` (TestUnknownMergeStateRejection: UNKNOWN rejects pos/neg, --auto bypass, READY merges)

## Tests
`uv run pytest tests/test_merge_pr.py` -> 45 passed. Mutation (UNKNOWN -> MUTANT)
made the two reject tests fail; restored to green.

## Note for future
`write_skill_error` valid error_type set does not include "Transient"; code 3
uses "ApiError" by existing convention in this script.
