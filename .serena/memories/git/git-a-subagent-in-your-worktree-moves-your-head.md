# A sub-agent pointed at a worktree moves your HEAD, and your next push publishes its commit

## The trap

Give a sub-agent a worktree path and it will run git there. Not a copy, the
worktree you are standing in. Checkout and switch land on your `HEAD`, your
index, and your working tree, and so does a merge that completes. A merge that
stops short leaves `HEAD` alone: a conflicted merge exits 1 with `MERGE_HEAD`
set and `HEAD` unmoved, and `--no-commit` does the same by request. Your files
are still rewritten either way. Branch creation alone is milder: it writes a
shared ref under `refs/heads/`, which every worktree sees, but it does not move
the current worktree's `HEAD`.

Once `HEAD` has moved, a later `git push origin HEAD:refs/heads/<your-branch>`
resolves `HEAD` to whatever the agent left checked out and publishes that
instead of your commit. `git push` resolves the `<src>` side once, when the
push starts.

Know what checkout will and will not destroy, because the reflex to blame it is
strong and usually wrong:

- Plain `git checkout <branch>` **refuses** when the switch would overwrite a
  tracked unstaged edit. It reports `Your local changes ... would be
  overwritten by checkout` and exits 1.
- It can silently overwrite **ignored** untracked files.
- The destructive forms need explicit syntax: `git checkout -- <path>` and
  `git checkout <tree-ish> -- <path>` overwrite the named paths, and
  `git checkout -f <branch>` discards conflicting local changes.

## What it looked like when it bit

Observed 2026-08-04 in `wt-idxchurn`. A `rubber-duck` reviewer was asked to
falsify a claim that two branches adding one memory each always collide on
`.serena/memories/memory-index.md`. It chose to verify empirically, which is
the right instinct, and created `test1` through `test4` and merged them, which
is the wrong place.

```
$ git branch --show-current
test4                                   # not my branch
$ git ls-remote origin refs/heads/docs/memory-index-token-churn
03b67dc58...                            # an old main commit, not my b7088964d
```

An unstaged `memory-index.md` edit was also absent afterward. The retained git
evidence does not identify the command that replaced it. The reflog records
`reset: moving to HEAD` entries but does not say whether any was a hard reset,
so this incident cannot attribute the loss to a plain branch checkout, and the
list above is why.

The erroneous ref update succeeded. Do not reach for a comforting explanation
of how it got past the gates: at the incident revision `lefthook.yml` carries
unscoped pre-push jobs including `pre-pr-validation`, `python-tests`, and
`build-all-check`, and the pushed commit did touch `.serena/memories/**/*.md`,
which several scoped jobs match. A green push is not evidence that you pushed
what you meant to.

## Do this instead

A reviewer that needs to run git gets a throwaway clone, never a worktree
someone else owns:

```bash
git clone --no-hardlinks <repo-path> ~/src/scratch/<agent>-sandbox
git -C ~/src/scratch/<agent>-sandbox remote remove origin
```

The second line is not optional. A local clone inherits a push-capable `origin`
pointing at the source checkout, so a reviewer can still update shared refs or
reach a production remote from inside its "sandbox". If the experiment needs a
remote, point it at a scratch bare repository.

`--no-hardlinks` is worth passing, for a narrower reason than it first appears.
A local-path clone normally hardlinks files under `.git/objects` when possible;
`--no-hardlinks` copies them, so the two repositories do not share object-file
inodes. Ordinary reads and writes were already logically independent, because
git objects are immutable. It also does not remove the documented race if the
source changes while the clone runs.

Say all of this in the delegation prompt rather than assuming it. The agent is
not doing anything unreasonable; it has a path and a question, and running the
experiment is the correct instinct. Give it somewhere safe to run.

## Push with a SHA, not with HEAD

```bash
git push origin <sha>:refs/heads/<branch>     # a literal SHA ignores HEAD
git push origin HEAD:refs/heads/<branch>      # resolves when the push starts
```

The SHA form is cheap and it removes this specific failure, a `HEAD` that
something else moved between your last look and the push. It does not make
pushing safe in general: you can still name the wrong destination ref, and it
says nothing about what another process does to the remote. This is scoped
advice, not a global rule. `HEAD:refs/heads/$BRANCH` is fine in a worktree no
other process touches, and other memories use it. Reach for the SHA form any
time an agent has touched, or might touch, the worktree you push from.

## Recovering a wrongly published branch

Check for a fast-forward before reaching for anything heavier, and test the
branch's **current** remote tip, not the SHA you remember it being pushed to.
The tip may have advanced since.

```bash
git fetch origin refs/heads/<branch>
git merge-base --is-ancestor FETCH_HEAD <correct-sha> && \
  git push origin <correct-sha>:refs/heads/<branch>
```

Fetch first. `git ls-remote` shows you the tip, but it does not bring the object
into your repository, so feeding its output straight to `git merge-base` can die
with `fatal: Not a valid commit name` and exit 128. That happens whenever the
advertised object is not already local, which is the ordinary case for a tip
someone else advanced, though you may get lucky if the commit arrived through
another ref. The `&&` still blocks the push, so it fails safe, but a check that
errors out tells you nothing. Fetching first makes the tip a real local object
and the predicate actually runs.

A plain push repairs the branch only when the current remote tip is an ancestor
of the intended SHA. In the incident above it was, because the wrong commit was
simply the branch point. Delete-and-recreate was drafted first and turned out to
be unnecessary. When the tip has advanced past your intended SHA the predicate
exits 1 and the push is skipped, which is the answer you want: that is no longer
a fast-forward, and someone else's work is sitting on the branch.

## Related

`git/git-shallow-is-shared-across-every-worktree.md` and
`git/git-stash-is-shared-across-every-worktree.md` are the same family: state
that looks local lives in the common git directory. The stash is already a ref,
`refs/stash`, so it and this memory are one mechanism rather than two. Branch
refs are the loud version, because a mistaken push can publish `refs/heads/*`
where other people can see it. A shared ref does not reach a remote on its own;
it takes an explicit push. That is the point, though, because the push you meant
to make is the one that carries it.

Be precise about which refs. `refs/heads/*` is shared across every worktree.
`HEAD` is per-worktree, and git documents further per-worktree exceptions:
`refs/bisect`, `refs/worktree`, and `refs/rewritten`.

`parallel/parallel-001-worktree-isolation.md` recommends worktrees for parallel
work and is not in tension with this. That is about worktrees you create for
your own PRs. This is about handing an existing one to an agent.
