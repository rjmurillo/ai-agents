# Concurrent pre-push gates fail on load, so heavy stages must wait, not skip

## What happened

[2026-10-14] About 16 agents ran pre-push gates on one host at the same time. The operator session saw load average 10 to 13; the logs do not record load. Clean pushes failed in three ways:

- testmon: `sqlite3.OperationalError: database is locked` in `testmon/db.py` `insert_test_file_fps`, failing the `tests` and `tests/mutation` lanes.
- pytest: `pytest partition tests: exit 3 in 180.1s, stopped at the 180s budget`.
- semgrep: `semgrep-core exited with code 1` and `Failed to obtain target files from semgrep-core`.

The same pushes passed later at load average about 2. No code changed between the runs.

A second data point: the first push of PR #6611 failed with `stopped at the 180s budget` at load average about 10. It passed unchanged once load fell below 5.

## Rule

Never skip a gate to make a push pass. A skipped gate looks green and proves nothing. Wait for headroom instead.

On a base without the #6609 fix, do this by hand:

- Keep about 3 heavy pushes running at once (see the `/tmp` inode memory).
- Before a push, wait until the 1-minute load average in `/proc/loadavg` is below about 5.

The #6609 fix is `scripts/validation/host_headroom.py`: a host-wide semaphore of 3 slots around pytest and semgrep. Each stage waits for a slot and for load below 8, then runs even if the wait ran out. `pre_pr.py` is not gated: its 240s budget fills its 4m cap. It caps load across all branches. It does not replace the per-branch push `flock` in `.claude/rules/push-lock.md`. That rule retired an older hashed four-slot lock because different branches collided in it.

## Caveats

- PR #6602 (merged 2026-10-14) gives each overlapping pytest lane its own testmon database. It fixed issue #6477, an xdist "Different tests were collected" failure. The lock above came from a base that predates #6602, so the lock may no longer reproduce. That is not verified under load.
- After #6609, pytest waits before its 180s clock starts. A semgrep-core target failure exits 3 and prints the host load.
- Each worktree already has its own `.testmondata`. The lock was within one push, not across worktrees.

## Sources

- Issue #6609 (log excerpts from `~/.cache/ai-agents-tmp/d2_push*.log`).
- PR #6602, issue #6477.
- Related: `.claude/rules/push-lock.md`, `ci/ci-tmp-inode-cap-stops-every-tool-call-during-parallel-pushes`, `orchestration/orchestration-the-wave-cap-lives-in-the-orchestrator-template-not-in-a-hand-written-brief`.
