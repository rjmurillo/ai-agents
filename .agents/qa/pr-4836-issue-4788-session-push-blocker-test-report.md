---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-4788-bacc8e40d-fix-historical-session-log-blocking.json
qaCommit: 0ec5463bbbafbfeed960aba73a076618b95f8435
---
# QA Report: PR 4836 session validation blockers

## Summary

PASS. The PR 4836 CI fixes cover the reported Validate PR, Run Python Tests, and review-thread blockers.

## Root Causes Verified

- `lefthook.yml` kept `session-json-validation` in a `parallel: true` pre-push group while it consumed stdin. It could race the shared pre-push stream.
- `scripts/validation/session_scope.py` classified committed HEAD paths from the ambient working tree. Unrelated unstaged deletions could change pre-push and pre-PR scope.
- Low-similarity session replacements were removed from the added set, which let callers downgrade full validation to `--existing-log`.
- `new_pr.py` read a session log from `head:<path>` but validated QA ancestry against the checked-out HEAD.
- `new_pr.py` reused the session basename directly in scratch storage, so concurrent validations of the same path could collide.
- `tests/test_push_range_filter.py` committed a symlink without test-local git identity. CI without global git config returned 128.

## Evidence

| Check | Result |
|-------|--------|
| `uv run --frozen ruff check scripts/validation/session_scope.py scripts/validation/git_hook_policy.py .claude/skills/github/scripts/pr/new_pr.py src/copilot-cli/skills/github/scripts/pr/new_pr.py tests/test_validate_session_json.py tests/test_new_pr.py tests/test_push_range_filter.py tests/test_lefthook_integration.py` | PASS |
| `uv run --frozen pytest tests/test_validate_session_json.py::TestSessionScopeIsDecidedOnceForBothCallSites tests/test_new_pr.py::test_session_log_temp_copy_preserves_the_original_basename tests/test_new_pr.py::TestRunValidations tests/test_new_pr.py::TestResolveValidationBase tests/test_new_pr.py::TestResolveValidationHead tests/test_new_pr.py::TestMainUsesResolvedValidationBase tests/test_push_range_filter.py::TestHandleSessions::test_a_committed_session_symlink_does_not_match_head tests/test_lefthook_integration.py -q` | 868 passed |
| `uv run --frozen pytest tests/test_new_pr.py -q` | 88 passed |
| `uv run --frozen pytest tests/ -x -q --tb=short` | 25565 passed, 36 skipped, 2 warnings |
| `uv run --frozen python build/scripts/build_all.py` | regenerated skill mirror, no drift after generation |

## Coverage

- Positive: added session paths, resolved validation heads, unique scratch copies, and valid stdin scheduling pass.
- Negative: historical records, missing branch-ref session logs, non-HEAD pushes, dirty session files, and symlink session paths fail closed.
- Edge: tab characters in paths, low-similarity delete/add replacements, untracked logs, and unresolved validation heads keep strict validation.

## Status

QA COMPLETE.
