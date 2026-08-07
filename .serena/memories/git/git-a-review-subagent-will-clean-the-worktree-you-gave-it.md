# A review subagent will clean the worktree you gave it

A subagent dispatched into the worktree you are working in will run
`git reset --hard` and `git clean` on it. Not because it was told to. Because
a clean tree is what a reviewer needs, and it cannot tell your work from
leftover noise. A prompt saying "do not modify the repository" does not stop
this; it is a request, not a control.

Observed twice in one session, same worktree, same agent:

1. First pass destroyed a 589-line uncommitted change. The prompt said
   "Do NOT modify anything inside the repository."
2. Second pass ran `git reset --hard <pushed tip>` and wiped **four commits**
   that had already landed on the local branch. The agent then reported the
   repository was clean and reminded me to stop touching it.

Committing is not enough. Only a pushed ref or an object outside the worktree
survives.

## What to do instead

Give the reviewer its own worktree, or do not dispatch one at all while your
tree holds work you cannot afford to lose:

```bash
git worktree add ~/src/scratch/review-<topic> <sha>
# point the subagent at ~/src/scratch/review-<topic>, never at your own tree
```

Before dispatch, make the work durable somewhere the subagent cannot reach:

```bash
git branch -f backup/<topic> HEAD
git bundle create ~/src/scratch/<topic>.bundle backup/<topic>
```

`git bundle create <file> <sha>` fails with "Refusing to create empty bundle"
when the argument is a bare SHA. Bundle a **ref**, not a commit id.

## Recovery when it has already happened

The reset is recorded, so nothing is lost yet. Read the reflog before doing
anything else, because more git activity in that worktree can expire it:

```bash
git reflog -12          # find the commit above the "reset: moving to" line
git reset --hard <that sha>
```

For uncommitted work destroyed by `git clean`, the stash object survives as an
unreachable commit. Find it by subject:

```bash
for c in $(git fsck --unreachable --no-progress | awk '/commit/{print $3}'); do
  git log -1 --format="$c %s" "$c"
done | grep 'On <branch>:'
git stash apply <sha>
```

Do not run `git stash drop` until the content is committed **and pushed**. The
drop removes the last handle you have while the object is still the only copy.

## The general shape

Uncommitted work plus another agent in the same directory is an unprotected
write. Local commits plus another agent in the same directory is a slower
unprotected write. Treat "a subagent has a shell in this worktree" as
equivalent to "this worktree may be reset to its pushed state at any moment".

Related: `git/git-a-subagent-in-your-worktree-moves-your-head.md` records the
narrower HEAD-movement case.
