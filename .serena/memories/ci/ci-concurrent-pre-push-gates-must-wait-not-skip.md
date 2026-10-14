# Concurrent pre-push gates fail on load, so heavy stages must wait, not skip

## What happened

[2026-10-14] About 16 agents ran pre-push gates on one host at the same time. Load average reached 10 to 13. Disk and inodes ran short. Clean pushes failed in three ways:

- testmon: `sqlite3.OperationalError: database is locked` in `testmon/db.py` `insert_test_file_fps`, failing the `tests` and `tests/mutation` lanes.
- pytest: `pytest partition tests: exit 3 in 180.1s, stopped at the 180s budget`.
- semgrep: `semgrep-core exited with code 1` and `Failed to obtain target files from semgrep-core`.

The same pushes passed later at load average about 2. No code changed between the runs.

## Rule

Gate heavy stages (pytest, semgrep, `pre_pr.py`) with a host-wide semaphore of 3 to 4 slots. Before a stage starts, wait for a slot and for disk and load headroom. Do not skip the stage to make the push pass. A skipped gate looks green and proves nothing.

## Caveats

- PR #6602 (merged 2026-10-14) gives each overlapping pytest lane its own testmon database. The lock above came from a base that predates it. It may no longer reproduce.
- Each worktree already has its own `.testmondata`. The lock was within one push, not across worktrees.

## Sources

- Issue #6609 (log excerpts from `~/.cache/ai-agents-tmp/d2_push*.log`).
- PR #6602, issue #6477.
- Related: `ci/ci-tmp-inode-cap-stops-every-tool-call-during-parallel-pushes`, `orchestration/orchestration-the-wave-cap-lives-in-the-orchestrator-template-not-in-a-hand-written-brief`.
