---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10035-bfffb0de4-create-report-4718-worktree-changes.json
qaCommit: 7a04a4a683926fe27cf60b0aac8fcd1b0794232d
---
# Test Report: PR #4718 GC worktree stale entries

## Scope

Branch `fix/gc-worktrees-stale-entries`, code tip
`7a04a4a683926fe27cf60b0aac8fcd1b0794232d`, against merge-base
`cefc2b0ed94e322624d4c41c0007822948ba2c81`.

The diff changes 27 GC files, 3099 insertions and 783 deletions. It splits
worktree-only anchor readers into dedicated helpers, tightens stale-worktree
probes, and adds real-git regression coverage for the commit-loss paths.

## Live state and setup

- Acquired the PR lease with `pr_autofix_lease.py` for `session-10035`.
- `check_pr_live_state.py` returned `ACT` for PR #4718, head
  `7a04a4a683926fe27cf60b0aac8fcd1b0794232d`, base `main` at
  `cefc2b0ed94e322624d4c41c0007822948ba2c81`.
- The first worktree checkout landed on stale local commit
  `7617a6d03031590b45dab6a17e1709bb902fbc3e`. I reset the worktree to
  `origin/fix/gc-worktrees-stale-entries` before testing. This report applies
  to `7a04a4a683926fe27cf60b0aac8fcd1b0794232d`.

## Test execution results

| Command | Result |
|---------|--------|
| `uv run pytest -q tests/gc_real_git.py tests/gc_stale_unit.py tests/test_gc_anchor_readers.py tests/test_gc_stale_probes.py tests/test_gc_worktrees.py tests/test_gc_worktrees_cli.py tests/test_gc_worktrees_occupancy.py tests/test_gc_worktrees_real_git.py` | 127 passed in 2.98s |
| `uv run pytest -q tests/test_gc*.py` | 297 passed in 10.59s |
| `python3 .claude/skills/github/scripts/pr/get_pr_checks.py --pull-request 4718 --required-only --output-format json` | `Validate PR` failed, five required checks were pending, failure matched the missing-QA state described in the PR context |

## Code review summary

Reviewed the GC maintenance diff and its new tests.

- `scripts/maintenance/_gc_anchors.py` adds tri-state readers for reflogs and
  worktree-local refs. Unreadable or malformed anchors return unknown, not an
  empty safe result.
- `scripts/maintenance/_gc_stale.py` now combines reflog and per-worktree ref
  anchors in `unreachable_admin_commits`, and tightens
  `linked_checkout_present` so the checkout at a path must still match the
  recorded admin entry.
- `scripts/maintenance/_gc_apply.py` adds last-moment rechecks before removal:
  compare HEAD against the recheck result, rerun the reflog-only orphan probe,
  rerun the suspended-operation probe, and re-verify checkout identity. This
  closes the race where HEAD returns to the same value or a commit lands during
  the orphan probe.
- New tests in `tests/test_gc_anchor_readers.py`,
  `tests/test_gc_worktrees_real_git_anchors.py`,
  `tests/test_gc_worktrees_real_git_apply.py`,
  `tests/test_gc_worktrees_real_git_stale.py`,
  `tests/test_gc_worktrees_stale.py`,
  `tests/test_gc_worktrees_stale_apply.py`, and
  `tests/test_gc_worktrees_stale_warnings.py` pin both positive loss channels
  and negative controls.

I did not find a correctness regression in the reviewed paths. The new tests
match the failure modes the patch is trying to close.

## Verdict

PASS. The targeted GC suite passed, the PR remained actionable during the run,
and the diff closes the reported worktree-only anchor loss paths with matching
unit and real-git coverage.
