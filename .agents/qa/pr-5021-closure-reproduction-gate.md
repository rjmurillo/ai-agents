---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-5021-closure-reproduction-gate.json
qaCommit: 287042d7bade7c3ef76de86edd74d61bbcf353e9
---

# PR 5021 Closure Reproduction Gate QA Report

## Scope

Validates the reproduction_verified gate added to _apply_close (issue #4624).

## Evidence

| Check | Result |
|---|---|
| Defect reproduction on main | Confirmed: close succeeds without reproduction |
| Negative test (PR cited, no reproduction) | SKIPPED with correct message |
| Positive test (PR cited, reproduction verified) | APPLIED |
| Edge test (no citation, no reproduction) | APPLIED (bypass correct) |
| Dry-run gate | Blocks correctly in planning mode |
| from_raw parsing (true) | Parsed correctly |
| from_raw parsing (default) | Defaults to false |
| from_raw parsing (non-bool) | Rejected, defaults to false |
| Full test suite | 107 tests passed |
| Ruff lint | All checks passed |
| mypy type check | 0 errors on 3 source files |
| Pre-PR validation | All validations passed |
| Pre-push hooks | All passed including python-tests (463.60s) |

## Acceptance Criteria

| Criterion | Status |
|---|---|
| Open PR cited is refused | PASS (via PR #4716 verify_pr_merged) |
| Merged PR not on main is refused | PASS (via PR #4716 ancestry check) |
| Merged PR on main requires green reproduction | PASS (this PR) |
| Refusal names PR state | PASS (via PR #4716) |
