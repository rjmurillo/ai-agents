---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-15002-issue-5071-mypy-diff-scope.json
qaCommit: ef7f749d1872c77f5141ee67ae8c165ba3161b4c
---

# QA Report: Issue 5071, pre-push mypy scoped to merge-base diff

**Date**: 2026-08-15
**Session**: 15002
**Branch**: claude/issue-5071-mypy-diff-scope
**Feature**: `run_mypy` file set filtered to files that still differ from the merge base

## Changes Tested

- `scripts/validation/git_hook_policy.py`: `_merge_base_scope` (name-only merge-base diff), `_filter_to_merge_base_scope` (scope filter with count report), wired into `run_mypy`
- `tests/test_lefthook_integration.py`: 8 new tests covering the scope filter

## Test Strategy

Unit tests over monkeypatched seams plus real-git integration tests, per TESTING-RIGOR
(positive, negative, edge), and a `main(argv)` exit-code test per the ci-scripts CLI
exit contract. A standalone git probe verified the underlying `git diff --name-only`
semantics for renames, deletions, and round trips before implementation.

## Test Results

### 1. Positive: modified file is still checked

**Test**: `test_mypy_scope_keeps_modified_file_and_blocks_its_errors`
**Result**: PASS
**Evidence**: File in scope with an error on a changed line returns 1 from `run_mypy`

### 2. Negative: round-tripped file contributes nothing

**Test**: `test_mypy_scope_round_trip_file_is_not_scanned`
**Result**: PASS
**Evidence**: `_invoke_mypy` recorded zero invocations; exit 0; scope report prints
"0 of 1 pushed file(s)" so an empty run is distinguishable from an unexamined run

### 3. Edge: rename, deletion, round trip against real git

**Test**: `test_merge_base_scope_drops_round_trip_keeps_modified_rename_deletion`
**Result**: PASS
**Evidence**: Scope keeps `keep.py` (modified), `new.py` (rename post-image),
`gone.py` (deleted, later dropped by the existing file-existence check); excludes
`round.py` (commit-then-revert)

### 4. Edge: empty diff and empty input

**Test**: `test_merge_base_scope_empty_paths_is_empty_set`; scope-to-empty covered by
test 2 (all candidates round-tripped exits 0)
**Result**: PASS

### 5. Edge: unresolvable merge base never weakens the gate

**Tests**: `test_merge_base_scope_returns_none_when_base_unresolved`,
`test_mypy_scope_fallback_scans_full_set_when_base_unresolved`
**Result**: PASS
**Evidence**: `None` scope keeps the full pushed set and the block-on-any-error
fallback still returns 1

### 6. Wiring: end-to-end over a real repository

**Test**: `test_mypy_scope_end_to_end_drops_round_trip_with_real_git`
**Result**: PASS
**Evidence**: `run_mypy` with real merge-base diff hands mypy only `keep.py`

### 7. CLI exit contract

**Test**: `test_mypy_cli_main_exit_codes_respect_merge_base_scope`
**Result**: PASS
**Evidence**: `policy.main(["--repo-root", ..., "mypy", "source.py"])` returns 1 for a
blocking error in scope and 0 when the same file round-tripped out of scope

## Regression Sweep

- `uv run --frozen python -m pytest tests/test_lefthook_integration.py -k "mypy or merge_base_scope or changed_line"`: 30 passed (22 pre-existing mypy/ratchet tests unchanged)
- `uv run --frozen python scripts/validation/pre_pr.py`: RESULT: All validations passed
- `ruff check` clean on both touched files; `mypy` clean on `git_hook_policy.py`
- Taste count ratchet: OK (count == baseline 583) after extracting the filter helper
  to keep `run_mypy` at complexity 10

## Pre-push Full-Suite Repair (found while pushing)

The full pre-push suite (selected because this change touches
`scripts/validation/git_hook_policy.py`) surfaced 20 failures unrelated to this
diff, all environmental in a root CCR container:

- 16 forgetful-import tests: `sqlite3` CLI missing. Fixed by adding `sqlite3`
  to `scripts/bootstrap-vm.sh` prerequisites.
- `test_a_signed_history_is_still_read`: `ssh-keygen` missing. Fixed by adding
  `openssh-client` to `scripts/bootstrap-vm.sh`.
- `test_the_tracked_scan_fails_config_on_an_unreadable_file` and
  `test_permission_denied_file_returns_auth_exit_code` (plus the two
  bundle-suite aggregates re-running the latter): both build their
  precondition from file mode bits, which root ignores. Guarded with the
  repo's existing `_NO_PERMISSION_BARRIER` skipif idiom
  (`tests/test_gc_anchor_readers.py`); the orphan-ref-validator mirror was
  regenerated via `build/scripts/build_all.py` and is byte-identical.

After the repairs: the three named tests pass or skip under root, and the
forgetful tests pass (41 passed).

## Acceptance Criteria Mapping (issue #5071)

- Commit-then-revert round trip contributes nothing to the mypy scope: tests 2, 3, 6
- Files actually modified vs merge-base are still checked: tests 1, 6
- Regression test covers the round-trip case: tests 2 and 6
