---
qaVerdict: PASS
qaCommit: 654b668325285da45d2ee1888f39c474473395c2
qaSessionLog: .agents/sessions/2026-08-15-session-5008-replacement.json
---

# QA Report: PR 5039 - Re-pin Worktree Identity + CI Backstop

## Summary

Fixes issue #5008 (both acceptance criteria):
1. Runtime: adds `reset_worktree_identity` call before cleanup commits with
   fail-closed error handling for config unset failures.
2. CI backstop: adds `placeholder-identity-check.yml` workflow that runs
   `check_placeholder_identity.py` on every PR to detect leaked identity
   before merge.

## Test Execution Evidence

```
$ uv run --frozen pytest tests/test_pr_autofix_worktree_identity.py tests/test_invoke_batch_pr_review.py -v
============================== 36 passed in 0.70s ==============================
```

## Scenarios Verified

### Runtime Reset (item 1)
1. Leaked identity replaced before cleanup commit (TestPushWorktreeChanges)
2. Clean worktree unchanged (TestPushWorktreeChanges)
3. Operator identity forwarded from CLI (TestPushWorktreeChanges)
4. Config unset failure (non-key-not-found) raises CalledProcessError (TestWorktreeIdentityReset)

### CI Backstop (item 2)
5. Workflow file exists (TestCIBackstopWorkflow)
6. Workflow calls check_placeholder_identity.py (TestCIBackstopWorkflow)
7. Workflow uses fetch-depth 0 for full history (TestCIBackstopWorkflow)
8. Workflow triggers on pull_request (TestCIBackstopWorkflow)

### Pre-existing regression tests (pass)
9. Placeholder author rejected (TestPlaceholderGuardRejectsCommits)
10. Placeholder committer rejected (TestPlaceholderGuardRejectsCommits)
11. Guard skips pytest tmp_path repos (TestGuardTmpPathExemption)

## Error Handling

`reset_worktree_identity` (lines 82-88 of `worktree_identity.py`):
- Return code 5 (key not found): treated as success (nothing to unset)
- Return code 0: success
- Any other return code: raises `subprocess.CalledProcessError` (fail-closed)

`determine_placeholder_range.py` (lines 47-51):
- Missing env var: raises `KeyError` -> `SystemExit(2)`
- git merge-base failure: raises `CalledProcessError` -> `SystemExit(2)`

## Linting

- ruff: clean (0 errors on changed files)
- mypy: clean (0 errors on changed files)
- cli-exit-contract-ratchet: 27 == 27 (unchanged)
