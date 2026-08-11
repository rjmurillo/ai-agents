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

1. Acquire the lease before creating or selecting the PR worktree.
2. Treat a bare root's `local_head_sha` as diagnostic mismatch evidence only.
3. Create or switch to the dedicated PR worktree.
4. Renew the lease from that worktree before branch mutation.
5. Verify local `HEAD`, remote branch tip, and PR head SHA match before push.
