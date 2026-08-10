---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-4788-bacc8e40d-fix-historical-session-log-blocking.json
qaCommit: 0f3eee31fcaa2cf59887282c3fdd71c9a4eb10d7
---
# QA Report: PR 4836 session validation blockers

## Summary

PASS. The PR 4836 CI fixes cover the reported Validate PR, Run Python Tests, Windows path tests, and review-thread blockers.

## Root Causes Verified

- `lefthook.yml` kept `session-json-validation` in a `parallel: true` pre-push group while it consumed stdin. It could race the shared pre-push stream.
- `scripts/validation/session_scope.py` classified committed HEAD paths from the ambient working tree. Unrelated unstaged deletions could change pre-push and pre-PR scope.
- Low-similarity session replacements were removed from the added set, which let callers downgrade full validation to `--existing-log`.
- `new_pr.py` read a session log from `head:<path>` but validated QA ancestry against the checked-out HEAD.
- `new_pr.py` reused the session basename directly in scratch storage, so concurrent validations of the same path could collide.
- `tests/test_push_range_filter.py` committed a symlink without test-local git identity. CI without global git config returned 128.
- `scripts/validate_session_json.py` applied new-log QA freshness checks to edited existing logs. Historical record validation failed when later branch commits changed unrelated code after the old QA commit.
- `scripts/validation/checks_tooling.py` filtered branch session logs through the dirty worktree and asked `new_session_logs()` without `compare_ref="HEAD"`. A deleted local worktree copy could skip pre-PR validation for a committed branch log.

## Evidence

| Check | Result |
|-------|--------|
| `uv run --frozen ruff check scripts/validation/session_scope.py scripts/validation/git_hook_policy.py .claude/skills/github/scripts/pr/new_pr.py src/copilot-cli/skills/github/scripts/pr/new_pr.py tests/test_validate_session_json.py tests/test_new_pr.py tests/test_push_range_filter.py tests/test_lefthook_integration.py` | PASS |
| `uv run --frozen pytest tests/test_validate_session_json.py::TestSessionScopeIsDecidedOnceForBothCallSites tests/test_new_pr.py::test_session_log_temp_copy_preserves_the_original_basename tests/test_new_pr.py::TestRunValidations tests/test_new_pr.py::TestResolveValidationBase tests/test_new_pr.py::TestResolveValidationHead tests/test_new_pr.py::TestMainUsesResolvedValidationBase tests/test_push_range_filter.py::TestHandleSessions::test_a_committed_session_symlink_does_not_match_head tests/test_lefthook_integration.py -q` | 868 passed |
| `uv run --frozen pytest tests/test_new_pr.py -q` | 88 passed |
| `uv run --frozen pytest tests/test_validate_session_json.py -q` | 346 passed |
| `uv run --frozen ruff check scripts/validation/checks_tooling.py tests/test_validation_pre_pr.py` | PASS |
| `uv run --frozen pytest tests/test_validation_pre_pr.py::TestValidateSessionEnd -q` | 7 passed |
| `uv run --frozen pytest tests/test_validation_pre_pr.py::TestValidateSessionEnd tests/test_validation_pre_pr_session_scope.py tests/test_validate_session_json.py::TestHistoricalLogsAreExemptByConstruction tests/test_validate_session_json.py::TestSessionScopeIsDecidedOnceForBothCallSites tests/test_validate_session_json.py::TestValidateQaReportEvidence -q` | 51 passed |
| `uv run --frozen --extra dev python scripts/ci/merge_tree_ratchet_check.py --base-ref origin/main` | PASS |
| `uv run --frozen python scripts/validate_session_json.py .agents/sessions/2026-08-08-session-10018-b2f6a78e7-fix-issue-3912-authoritative-github.json --scope-from-git --validation-head HEAD` | PASS |
| `uv run --frozen pytest tests/ -x -q --tb=short` | 25565 passed, 36 skipped, 2 warnings |
| `uv run --frozen python build/scripts/build_all.py` | regenerated skill mirror, no drift after generation |

## Coverage

- Positive: added session paths, resolved validation heads, unique scratch copies, and valid stdin scheduling pass.
- Negative: missing branch-ref session logs, non-HEAD pushes, dirty session files, and symlink session paths fail closed.
- Edge: historical edited logs remain record-only, dirty worktree session deletions fail closed, tab characters in paths, low-similarity delete/add replacements, untracked logs, and unresolved validation heads keep strict validation.

## Status

QA COMPLETE.
