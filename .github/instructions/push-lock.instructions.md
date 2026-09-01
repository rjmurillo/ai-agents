---
applyTo: .agents/governance/**,.serena/memories/**,.claude/**
---

# One Push Lock Path

Scoped to the trees that carry push recipes rather than `**`. The always-on
`.md` ceiling in `scripts/validation/instruction_budget.py` had 998 bytes of
headroom when this rule was written and a universal copy failed it at 102.7
percent, which blocks every contributor's push. Nothing is lost by the narrower
scope: the binding half is
`scripts/validation/check_push_lock_paths.py`, which `pre_pr.py` runs on every
push whatever rules the harness loaded.

`flock` excludes only processes that open the same path. Two agents pushing the
same branch under two different lock names run concurrently while both believe
they are serialized, which is the lost ref update the lock exists to prevent.

Three schemes were live at once on 2026-08-02 (issue #4366). A `ps` census taken
while roughly 20 push processes were running found 5 processes on the per-branch
scheme, 11 on a hashed four-slot scheme, and 2 on a `$HOME` variant. Two of the
three provided no exclusion against the other two.

The rule is one path, written the same way everywhere:

```bash
BR=$(git branch --show-current)
SLUG=$(printf '%s' "$BR" | tr '/' '-')
mkdir -p "$HOME/src/scratch/locks"
flock "$HOME/src/scratch/locks/push-lock-$SLUG.lock" git push origin "$BR"
```

## MUST

1. **Use `$HOME/src/scratch/locks/push-lock-<slug>.lock` and nothing else.** Not
   `/tmp`, not a hashed slot, not a literal home directory, not a per-worktree
   filename. A recipe that names any other path is a fourth scheme, and a fourth
   scheme is only discoverable by `ps`.
2. **Key the lock on the branch, with `/` replaced by `-`.** A branch named
   `fix/foo` writes a lock path with a `/` in the filename otherwise, which the
   shell reads as a directory. Two distinct branches must never share a lock:
   git takes its own lock per ref, so unrelated branches serializing behind a
   10 to 16 minute pre-push hook is pure waste. The hashed four-slot scheme
   collided two different branches about 25 percent of the time.
3. **Create the directory in the same command.** `flock` fails when the parent
   directory is missing, and a failed `flock` in a detached push is silent.
4. **Keep the lock out of `/tmp`.** `/tmp` was wiped mid-session on 2026-08-02.
   A wipe while a push holds the lock leaves the holder's descriptor on a
   deleted inode while the next push creates a new inode at the same path, so
   the two stop excluding each other. That is a split lock under one filename,
   which no amount of name agreement fixes.

## MUST NOT

1. MUST NOT write a machine-specific home directory into a recipe. `$HOME`
   expands per user; `/home/<name>` is how the third scheme was born.
2. MUST NOT introduce a second lock path "just for this run". The whole value of
   the lock is that every writer agrees on the name.

## Historical measurements

A `ps` census or a retrospective that records what the old schemes looked like
is evidence, not a recipe, and must not be rewritten to match this rule. Mark
such a fenced block, or such a paragraph of prose, with the token
`push-lock-historical` on a line inside it so
`scripts/validation/check_push_lock_paths.py` skips it. The checker
scans prescriptive surfaces only and leaves `.agents/retrospective/`,
`.agents/audits/`, and `.agents/archive/` alone.

## Commit guard

Issue #5123: the lock also gates new commits, not only concurrent pushes. A
commit landing in a worktree while a push for the same branch (in that
worktree or any other checkout of it) is still running its pre-push suite (6
to 15 minutes) can corrupt any test whose fixture reads live git state,
because git runs the pre-push hook inside the `git push` invocation the lock
already wraps, so the lock stays held for the full suite, not just the ref
transfer.

`scripts/validation/check_push_lock_before_commit.py` runs as the
`push-lock-commit-guard` pre-commit job in `lefthook.yml`. It reads the SAME
canonical lock file this rule defines and refuses the commit only while that
file is held by another process right now, i.e. while a push is in flight
for this branch name on this machine. It never creates or holds the lock
itself; a non-blocking probe of lock state is not a second scheme under MUST
NOT 2 above, it is a read of the one the recipe already takes.

The lock carries no worktree component (MUST 1 above), so this guard's
scope is exactly the lock's scope: per branch name per machine, not per
worktree. Two worktrees on the same branch name contend for the same lock
and the same guard; two worktrees on different branch names never do. The
same collapse applies here as in MUST 2: two branch names that only differ
by `/` (`a/b` and `a-b`) share one lock file and therefore one guard.

A commit refused this way is not lost. Wait for the in-flight push to finish
(or for its pre-push suite to fail and release the lock), then commit again.
If the lock is stuck (the holder crashed without releasing it), set
`SKIP_PUSH_LOCK_COMMIT_GUARD=1` to bypass this one check.

Known limitation: this is a point-in-time probe, not a held lock across the
commit. It runs early in the piped `pre-commit` sequence and releases the
lock immediately, so a push can still acquire the lock during a later
pre-commit job and start its pre-push suite before `git commit` finishes
updating HEAD. It narrows the race issue #5123 describes; it does not close
it. Closing it fully would need the commit and push paths to share one held
lock across their complete mutation windows, which this design does not do.

## Checking

```bash
uv run python scripts/validation/check_push_lock_paths.py
```

Exits 0 and prints the examined file count when every prescription agrees.
Exits 1 and names file, line, and offending path otherwise.

The unit is the block, not the line. A recipe reaches its lock four
ways and only the first keeps `flock` and the path on one line: inline,
through a variable (`LOCK=...` then `flock "$LOCK"`), through a file
descriptor (`exec 9>...` then `flock -n 9`), and across a `\` continuation.
Every lock a block opens must be canonical, read from its `.lock` tokens, its
`flock` argument, and its `exec` redirect target. Reading the argument is what
catches a lock written without the `.lock` suffix, and what keeps a dead scheme
visible when it shares a fence with the canonical recipe. The inventory comes
from the index, so a staged but uncommitted file is checked.

A recipe does not become canonical by losing its fence, so unfenced prose is
read the same way, one Markdown paragraph at a time: a blank line bounds the
unit, so a variable set in one paragraph never resolves a `flock` in another.
The one asymmetry is that only a fence is reported for naming no canonical
path at all, because prose discusses `flock` without prescribing anything
(issue #4635).

## References

- Issue #4366. The three-scheme census and the `/tmp` wipe.
- Issue #4283. The 28-waiter convoy the global lock produced.
- `.agents/governance/GOTCHAS.md`. The push recipe that carries this path.
