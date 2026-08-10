---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10035-bfffb0de4-create-report-4718-worktree-changes.json
qaCommit: 49a0cc9224b49d2def524d44406aa108045c893d
---
# Test Report: PR #4718 GC worktree stale entries

## Scope

Branch `fix/gc-worktrees-stale-entries`, code tip
`49a0cc9224b49d2def524d44406aa108045c893d`, against current `origin/main`.

The follow-up change fixes the required `Run Python Tests` failure from the
subprocess encoding count ratchet. It adds `errors="replace"` to branch-added
text-mode subprocess calls in the GC real-git tests.

## Live state and setup

- Acquired the PR lease with `pr_autofix_lease.py` for `autofix-qa-c-4718`.
- `check_pr_live_state.py` returned `ACT` for PR #4718, head
  `6bfd506f5fb0d2d60719d4a034579c825eda9d31`, base `main` at
  `b5f79b4f0423b062576776b71d01c17b0694e404`, before the CI fix.
- Reproduced the CI failure locally with
  `uv run --frozen python scripts/ci/subprocess_encoding_count_ratchet.py --base-ref FETCH_HEAD`.

## Test execution results

| Command | Result |
|---------|--------|
| `uv run --frozen pytest -q tests/test_gc_anchor_readers.py tests/test_gc_worktrees_real_git_anchors.py tests/test_gc_worktrees_real_git_healthy.py tests/test_gc_worktrees_real_git_stale.py` | 64 collected, 64 passed |
| `uv run --frozen python scripts/ci/subprocess_encoding_count_ratchet.py --base-ref FETCH_HEAD` | Passed, 236 violations <= baseline 253 |

## Code review summary

Reviewed the subprocess decoding diff. The change only adds the missing
`errors="replace"` keyword to existing text-mode subprocess calls. It does not
change command arguments, assertions, or fixture behavior.

- Current session reran `uv run --frozen python scripts/ci/subprocess_encoding_count_ratchet.py --base-ref FETCH_HEAD` and got 236 violations <= baseline 253.

## Verdict

PASS. The targeted GC suite passed, and the failed CI ratchet now passes against
current `origin/main`.
