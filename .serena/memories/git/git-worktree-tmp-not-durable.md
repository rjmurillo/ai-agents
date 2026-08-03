# Never Put a Git Worktree in /tmp

**Atomicity**: 96%
**Category**: Git Operations
**Source**: 2026-08-01 autopilot campaign, measured loss

## Statement

Create worktrees as siblings of the repository, never under `/tmp`. `/tmp` is
reclaimed without warning on this machine, and a reclaimed worktree takes every
uncommitted resolution with it.

## Context

Applies to any long-running or parallel session that spins up worktrees, and to
every agent prompt that tells a sub-agent where to put one. The window between
`git worktree add` and a successful `git push` is 7 to 15 minutes here, because
the pre-push suite runs inside `git push`. That window is long enough to lose a
worktree to a `/tmp` sweep.

## Evidence

A four-conflict merge resolution for PR #4003 was completed, verified (293 tests
plus 11 guard tests green, all three count ratchets green), and committed to a
worktree at `/tmp/wt_4003`. Mid-session `/tmp` was reclaimed. Afterwards:

```
$ cd /tmp/wt_4003
WORKTREE GONE
$ git rev-parse origin/fix/memory-cluster | cut -c1-9
d39ddfbf3        # still the pre-merge head; the push never landed
```

`/tmp` fell from ~200 entries to 119, taking the worktree, the saved resolved
files under `/tmp/keep4003`, and the in-flight push log. The commits existed only
in the worktree's own object store, so nothing was recoverable from the main
repository. Roughly two hours of resolution work was lost.

Committing does NOT protect you. A worktree carries its own working copy, and a
commit that has not been pushed lives only inside that worktree's directory tree.

## Pattern

```bash
cd /home/richard/src/GitHub/rjmurillo/ai-agents3 && git fetch origin
git worktree add -b fix/<slug> \
  /home/richard/src/GitHub/rjmurillo/ai-agents-<slug> origin/main
cd /home/richard/src/GitHub/rjmurillo/ai-agents-<slug>
```

The sibling convention is already established: 227 registered worktrees follow
`~/src/GitHub/rjmurillo/ai-agents-<slug>`.

Scratch logs and throwaway scripts may still live in `/tmp`. Anything you would
be unhappy to redo must not.

## Counter-intuition

The reflex is that `/tmp` is the right home for a temporary directory, and a
worktree is by name temporary. It is not temporary in the relevant sense: it is
the sole copy of unpushed work. Durability should be chosen by what the directory
holds, not by what its lifecycle is called.

## Related

- [git-worktree-parallel](git-worktree-parallel.md)
- [git-worktree-cleanup](git-worktree-cleanup.md)
