# A worktree whose directory is gone can still be removed by path

## The short version

Four facts about stale worktree entries, all measured against git 2.43.0. Each
one contradicts an assumption that looked obviously true.

| Assumption | Reality |
| --- | --- |
| You need `os.path.isdir` to detect a stale entry | Porcelain already tells you: `prunable <reason>` |
| `git worktree remove` needs the directory to exist | Exit 0 on a stale entry, no `--force` needed |
| `git worktree prune` is all or nothing | `git worktree lock` makes it selective |
| `branch --contains` plus `tag --contains` covers the refs | It misses `refs/stash`; use `for-each-ref --contains` |

## Porcelain marks staleness for you

`git worktree list --porcelain` emits a `prunable` line for any entry whose
working tree is gone:

```
worktree /home/richard/src/scratch/wt-old
HEAD 1a2b3c4d5e6f7890abcdef1234567890abcdef12
detached
prunable gitdir file points to non-existent location
```

Prefer this over probing the filesystem. It is git's own judgement rather than
an inference, it costs no extra syscall because you are already running the
command, and in a tool with tests it leaves fixtures alone. A fixture that
builds a worktree record with a made-up path like `/wt/a` fails an `isdir`
probe and passes a `prunable` check, which is the difference between rewriting
every fixture and rewriting none.

## Removal works on an entry with no directory

This is the one that matters, because getting it wrong pushes you toward
`prune`, and `prune` is the blunt instrument.

```bash
git worktree add /tmp/wt-demo -b demo && rm -rf /tmp/wt-demo
git worktree remove /tmp/wt-demo   # exit 0, admin record gone
```

No `--force`. The natural assumption is that `remove` has to enter the
directory to check for uncommitted work, so a missing directory would be an
error. It is not: git treats "nothing there" as "nothing to lose".

The consequence for any tool that cleans worktrees: you never need a blanket
prune. Every entry, live or stale, goes through the same per-path removal. That
buys three things at once. You cannot remove an entry your safety check never
examined, because there is no second code path. One unsafe entry no longer
blocks cleanup of the safe ones, because a withhold is per entry. And your
report of what was removed is a record rather than an assumption, because you
removed them one at a time and watched each result.

## Prune is selective if you lock

`git worktree prune` takes no path argument, which reads as all-or-nothing. It
is not. A locked entry is skipped:

```bash
git worktree lock /path/to/keep
git worktree prune              # everything else stale goes, this one stays
git worktree unlock /path/to/keep
```

Verified including the case that matters: a locked stale entry with a detached
HEAD survived, and its commit stayed reachable.

Know it, but reach for per-path `remove` anyway. The lock/prune/unlock dance
leaves user-visible state in the middle, so a run interrupted between the lock
and the unlock strands a lock that silently blocks every later cleanup, with
nothing pointing at the cause. Note also that once locked, porcelain stops
emitting `prunable` for that entry and emits `locked` instead, so a staleness
check that runs after the lock sees a different world than one that ran before.

## Use for-each-ref for reachability, not branch and tag

Before removing a worktree with a detached HEAD, confirm some ref contains it,
or the commit loses its last anchor.

```bash
git for-each-ref --contains "$sha" --count=1 --format='%(refname)'
```

Non-empty means something holds it. This walks **every** namespace, including
`refs/stash`, which `git branch --contains` and `git tag --contains` together
do not. A commit whose only anchor is a stash entry is anchored.

What it does not see: another worktree's detached `HEAD`. `HEAD` is
per-worktree and is not a ref under `refs/`. So a commit held only by a second
detached worktree reads as unreachable. That errs toward keeping the worktree,
which is the direction you want, but do not describe the check as complete.

Cost is not a reason to skip it. Measured at 0.066s per call against 3269 refs,
so even 62 entries is about four seconds.

## Rescuing one afterward

If a check says unreachable, put the SHA in the message, not just the path. The
next reader needs a runnable command, and once the admin entry is gone the SHA
is unrecoverable from the plan:

```bash
git branch rescue/<name> <sha>
```

A plan file that records `path`, `branch`, and `reason` but no SHA cannot
answer "what did we nearly lose" after the fact. Record identifiers, not
labels.

## Related

`git/git-worktree-cleanup.md` covers the routine session-end sweep of live
worktrees. This memory is the stale-entry case that sweep does not reach.
`parallel/parallel-001-worktree-isolation.md` is why there are enough worktrees
for any of this to matter.
