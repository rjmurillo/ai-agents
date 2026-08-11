---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-14653-b9e2467b9-issue-4843-default-branch-detection.json
qaCommit: 093b588e394b9dccf144d62e4b68f79c299afbee
---

# QA Report: Issue #4843 -- Default Branch Detection

**Date**: 2026-08-10
**Commit**: 093b588e394b9dccf144d62e4b68f79c299afbee
**Worktree**: `C:\Users\rimuri\.copilot\session-state\9d8546d8-9a5c-4572-b4f9-94f87bdf5a8d\files\issue-4843`

## Scope

Validate that omitting `--base` triggers automatic detection of the repository default branch in `new_pr.py` and `new_validated_pr.py`.

### Requirements Verified

| Requirement | Status |
|-------------|--------|
| Omitted `--base` detects `origin/HEAD` | [PASS] |
| Validates target ref exists before returning | [PASS] |
| Falls back remote then local main/master/dev, then hard "main" | [PASS] |
| Explicit `--base` bypasses detection | [PASS] |
| Wrapper omits unset `--base` from skill args | [PASS] |
| Canonical and generated mirror match (SHA256) | [PASS] |

### Files Changed

- `.claude/skills/github/scripts/pr/new_pr.py` -- added `_detect_default_branch`, `_git_ref_exists`, changed `--base` default to `""`
- `scripts/new_validated_pr.py` -- wrapper conditionally forwards `--base`
- `src/copilot-cli/skills/github/scripts/pr/new_pr.py` -- generated mirror (identical)
- `tests/test_new_pr.py` -- 13 new tests in `TestDetectDefaultBranch`, 2 orchestration tests
- `tests/test_new_validated_pr.py` -- 2 updated, 1 renamed test

## Test Execution

### 1. Focused unit tests: `TestDetectDefaultBranch` (13 tests)

**Command**: `python -m pytest tests/test_new_pr.py -k "TestDetectDefaultBranch" -v --override-ini='addopts='`

```
tests/test_new_pr.py::TestDetectDefaultBranch::test_real_git_validates_origin_head_target PASSED
tests/test_new_pr.py::TestDetectDefaultBranch::test_uses_origin_head PASSED
tests/test_new_pr.py::TestDetectDefaultBranch::test_preserves_slashes_in_origin_head_branch PASSED
tests/test_new_pr.py::TestDetectDefaultBranch::test_dangling_origin_head_uses_existing_fallback PASSED
tests/test_new_pr.py::TestDetectDefaultBranch::test_falls_back_to_existing_remote_candidate PASSED
tests/test_new_pr.py::TestDetectDefaultBranch::test_remote_candidate_precedes_local_candidate PASSED
tests/test_new_pr.py::TestDetectDefaultBranch::test_known_candidate_priority[refs/remotes/origin-existing0-main] PASSED
tests/test_new_pr.py::TestDetectDefaultBranch::test_known_candidate_priority[refs/remotes/origin-existing1-master] PASSED
tests/test_new_pr.py::TestDetectDefaultBranch::test_known_candidate_priority[refs/heads-existing2-main] PASSED
tests/test_new_pr.py::TestDetectDefaultBranch::test_known_candidate_priority[refs/heads-existing3-master] PASSED
tests/test_new_pr.py::TestDetectDefaultBranch::test_falls_back_to_existing_local_candidate PASSED
tests/test_new_pr.py::TestDetectDefaultBranch::test_falls_back_to_main_when_no_known_ref_exists PASSED
tests/test_new_pr.py::TestDetectDefaultBranch::test_falls_back_to_main_outside_git_repository PASSED
```

**Result**: 13 passed in 17.23s

### 2. Real-git scenario test

`test_real_git_validates_origin_head_target` creates an actual git repo with `origin/HEAD -> origin/master`, asserts detection returns `"master"`, then deletes the remote ref and asserts fallback to `"main"` via local `refs/heads/main`.

**Result**: [PASS] (included in run above)

### 3. Parser default test

**Command**: `python -m pytest tests/test_new_pr.py -k "base_defaults_to_auto" -v --override-ini='addopts='`

```
tests/test_new_pr.py::TestBuildParser::test_base_defaults_to_auto_detection PASSED
```

**Result**: 1 passed in 34.99s

### 4. Orchestration integration tests

**Command**: `python -m pytest tests/test_new_pr.py -k "omitted_base_uses_detected or validation_base_uses_origin" -v --override-ini='addopts='`

```
tests/test_new_pr.py::TestMainUsesResolvedValidationBase::test_validation_base_uses_origin_ref_not_local PASSED
tests/test_new_pr.py::TestMainUsesResolvedValidationBase::test_omitted_base_uses_detected_branch_for_validation_and_github PASSED
```

Key assertions verified:
- Explicit `--base main` calls `mock_detect.assert_not_called()` confirming bypass
- Omitted `--base` uses detected branch for both `run_validations` (`origin/master`) and `gh pr create` (`master`)

**Result**: 2 passed in 32.94s

### 5. Wrapper tests (`new_validated_pr.py`)

**Command**: `python -m pytest tests/test_new_validated_pr.py -k "omits_default_base or omits_optional_flags or forwards_every" -v --override-ini='addopts='`

```
tests/test_new_validated_pr.py::TestDispatch::test_omits_default_base_for_skill_detection PASSED
tests/test_new_validated_pr.py::TestDispatch::test_omits_optional_flags_when_unset PASSED
tests/test_new_validated_pr.py::TestDispatch::test_forwards_every_optional_flag PASSED
```

Key assertions: `--base` absent from skill command when unset; present when explicit.

**Result**: 3 passed in 28.09s

### 6. Ruff lint

**Command**: `python -m ruff check .claude/skills/github/scripts/pr/new_pr.py scripts/new_validated_pr.py tests/test_new_pr.py tests/test_new_validated_pr.py`

```
All checks passed!
```

**Result**: [PASS] -- 0 violations

### 7. Mirror integrity

```
Canonical SHA256: 2827FD93FFADBF3A4E5B74D7EF4AD94144FC826D9BC0DA8BAD01D3E4C8DA9FC2
Generated SHA256: 2827FD93FFADBF3A4E5B74D7EF4AD94144FC826D9BC0DA8BAD01D3E4C8DA9FC2
Match: True
```

**Result**: [PASS]

## Summary

| Metric | Value |
|--------|-------|
| Total tests run | 19 |
| Passed | 19 |
| Failed | 0 |
| Skipped | 0 |
| Ruff violations | 0 |

## Notes

- Four pre-existing full-file Windows test failures documented in the parent transcript are unrelated to this change and not attributed here.
- The `pytest-timeout` plugin is not installed in this environment; tests ran with `--override-ini='addopts='` to bypass the configured `--timeout=120`.

## Verdict

**QA COMPLETE**
