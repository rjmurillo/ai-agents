---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-5220-session-log-false-positive.json
qaCommit: fb0f0fa15b6dd0d20c1f2d75650dcc991f78ebaf
---

# QA Report: Issue #5220, check_branch_context hard-blocks after a merge when origin/HEAD is unset

## Summary

PASS. `_is_merged_history` now resolves the upstream default branch through a
fallback ladder (`origin/HEAD`, then `origin/main`, then `main`) instead of
depending on `origin/HEAD` alone, matching the ladder `resolve_push_update`
already uses for push-base resolution.

## Root Cause Verified

`_is_merged_history` in `scripts/validation/git_hook_policy.py` asked only
`git rev-parse --abbrev-ref origin/HEAD` and returned `False` the moment that
ref failed to resolve. `git clone` sets `origin/HEAD`; a fetch into an
already-initialised repo, a shallow or filtered clone, and several CI checkout
actions do not. Reproduced on this checkout before the fix:

```text
$ git rev-parse --abbrev-ref origin/HEAD
fatal: ambiguous argument 'origin/HEAD': unknown revision or path not in the working tree.
rc=128
$ git rev-parse --abbrev-ref origin/main
origin/main
rc=0
```

With `origin/HEAD` unresolved, `check_branch_context` blocked with the same
log names issue #5220 reports (`claude/pr-automerge-goal-eu2soz`,
`2026-08-21-session-99926-a1b2c3d4e-pr-automerge-goal.json`), confirming this
checkout hits the exact defect the issue describes.

## Evidence

| Check | Result |
|-------|--------|
| `uv run --frozen python -m pytest tests/test_lefthook_integration.py -k "branch_context" -q` | 21 passed |
| `uv run --frozen python -m pytest tests/test_lefthook_integration.py -q` | 864 passed, 1 skipped |
| `uv run --frozen ruff check scripts/validation/git_hook_policy.py tests/test_lefthook_integration.py` | All checks passed |
| `uv run --frozen mypy scripts/validation/git_hook_policy.py` | Success: no issues found in 1 source file |
| `uv run --frozen python scripts/validation/pre_pr.py` | 57 passed, 0 failed, 0 skipped |

## Coverage

- **Positive**: `test_branch_context_merged_history_survives_missing_origin_head`
  proves the exemption still fires when `origin/HEAD` is absent, the winning
  log is merged history reachable only via `origin/main`, and the branch owns
  its own log. Negative control inside the same test asserts `origin/HEAD`
  really is unresolved in the fixture, so the assertion cannot pass for the
  wrong reason.
- **Negative** (pre-existing, re-run to confirm no regression):
  `test_branch_context_blocks_a_newer_log_that_is_not_upstream` and
  `test_branch_context_merged_history_exemption_needs_an_upstream` still block
  a genuinely non-upstream newer log and a repo with no upstream ref at all.
- **Edge** (pre-existing, re-run to confirm no regression):
  `test_branch_context_survives_a_committed_merge_import` still requires the
  branch to own its own log before the exemption fires;
  `test_branch_context_fails_open_when_git_is_unavailable` still fails open
  when the `git` binary itself is missing.

## Status

QA COMPLETE.
