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
TOPIC=my-review-topic
SHA=$(git rev-parse HEAD)
git worktree add "$HOME/src/scratch/review-$TOPIC" "$SHA"
# point the subagent at that path, never at your own tree
```

Before dispatch, make the work durable somewhere the subagent cannot reach:

```bash
git branch -f "backup/$TOPIC" HEAD
git bundle create "$HOME/src/scratch/$TOPIC.bundle" "backup/$TOPIC"
```

Write these with shell variables, not with angle-bracket placeholders. `<topic>`
and `<sha>` are redirection operators: `git worktree add ~/x-<topic> <sha>` is a
hard syntax error, and `git branch -f backup/<topic> HEAD` is worse, because it
parses cleanly, reads from a file named `topic`, and truncates a file named
`HEAD`. A memory whose commands are copy-pasted is a memory whose placeholders
must survive being copy-pasted.

`git bundle create <file> <sha>` fails with "Refusing to create empty bundle"
when the argument is a bare SHA. Bundle a **ref**, not a commit id.

## Recovery when it has already happened

The reset is recorded, so nothing is lost yet. Read the reflog before doing
anything else, because more git activity in that worktree can expire it:

```bash
git reflog -12          # find the commit above the "reset: moving to" line
git reset --hard "$RECOVERY_SHA"
```

Work that was stashed and whose stash entry was then **dropped** survives as an
unreachable commit until it is pruned. Find it by subject:

```bash
for c in $(git fsck --unreachable --no-progress | awk '/commit/{print $3}'); do
  git log -1 --format="$c %s" "$c"
done | grep "On $BRANCH:"
git stash apply "$STASH_SHA"
```

This path exists only because something created a stash first. `git reset
--hard` and `git clean` create no stash object, so work destroyed by either,
having never been added or stashed, has **no** equivalent recovery. That is the
whole reason the backup above happens before dispatch rather than after the
loss. The recovery in this incident worked because the content had been stashed
and the stash was later dropped, not because `clean` left something behind.

Do not run `git stash drop` until the content is committed **and pushed**. The
drop removes the last handle you have while the object is still the only copy.

## The general shape

Uncommitted work plus another agent in the same directory is an unprotected
write. Local commits plus another agent in the same directory is a slower
unprotected write. Treat "a subagent has a shell in this worktree" as
equivalent to "this worktree may be reset to its pushed state at any moment".

Related: `git-a-subagent-in-your-worktree-moves-your-head.md` records the
narrower HEAD-movement case.
