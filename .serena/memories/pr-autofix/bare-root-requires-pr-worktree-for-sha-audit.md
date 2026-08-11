# PR autofix: bare root requires PR worktree for SHA audit

## Rule

When the repository is opened from a top-level bare checkout (`core.bare=true`),
use the dedicated PR worktree for lease renewal, SHA audit, merge-forward, and
push operations.

## Why

GitHub helper scripts can run from the bare root, but
`pr_autofix_lease.py acquire` reports that checkout's `HEAD` as
`local_head_sha`. A bare root is not the PR branch tip, so the value is
diagnostic mismatch evidence, not branch freshness evidence.

## Evidence

PR #4762 on 2026-08-07:

- Acquire from the bare root returned
  `local_head_sha=4bd7890864bfd29dc64d5cb96180d87a27031021`.
- The live PR head was `a75687064082d26c2a06f7b13defd169ecf7dc46`.
- Renewing from the PR worktree returned the live PR head SHA.

## Operational pattern

1. Use helper scripts from the bare root only for read-only PR context.
2. Switch to the dedicated PR worktree before branch mutation.
3. Renew or acquire the lease there.
4. Verify local `HEAD`, remote branch tip, and PR head SHA match before push.
