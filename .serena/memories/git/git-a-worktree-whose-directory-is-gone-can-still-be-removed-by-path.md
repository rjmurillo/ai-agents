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

## Correction: exit 0 does not mean nothing was lost

An earlier version of this page read the exit code as permission. It is not.
Two facts, both measured, retract that:

`prunable` does not mean the worktree is gone. A worktree that was **moved**
reports `prunable gitdir file points to non-existent location` and still works
perfectly at its new location. Git is reporting that it lost track of the
directory, not that the directory stopped existing. Nothing in the porcelain
output separates deleted from moved.

The admin `index` outlives the directory. `git add` writes a blob to the object
database and records it only in that worktree's index. `rm -rf` on the
directory leaves the index behind holding the blob's sole reference. Both
`git worktree remove` and `git worktree prune` then delete the admin directory,
index included, and the blob is reachable from nothing. `remove` returns exit 0
while doing it.

So "nothing there" is git's view of the *directory*, and it says nothing about
the object database. Report stale entries; do not remove them. Point the
operator at `git worktree prune --expire=<concrete age>`, and check the
orphaned index first, because that command is itself the data-loss path.

## Two traps when you check that index

Do not run git with `cwd` set to the admin directory. It fails with
`fatal: cannot use bare repository '...' (safe.bareRepository is 'explicit')`,
exit 128. Run from the main worktree with `GIT_INDEX_FILE` pointing at the
admin index instead:

```bash
GIT_INDEX_FILE=<admin>/index git diff-index --cached --quiet <head-sha>
```

Exit 0 is clean, exit 1 is staged content, and **anything else is git refusing
to answer**. A two-valued fail-closed check reads 128 as "staged" and warns on
every entry, which is the same as warning on none. Make the probe three-valued.

`git rev-parse --git-common-dir` answers relatively whenever it can. From the
repository root it returns `.git`; from a subdirectory, `../.git`. `git -C`
does not change this. Resolve it against the main worktree's path, never
against the process working directory, or the lookup fails everywhere except
the one directory you happened to test in.

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

Mechanically, yes. Safely, no: read the correction above before acting on this
section. It is recorded because the exit code surprises people, not because it
is a green light.

```bash
git worktree add ~/src/scratch/wt-demo -b demo && rm -rf ~/src/scratch/wt-demo
git worktree remove ~/src/scratch/wt-demo   # exit 0, admin record gone
```

No `--force`. The natural assumption is that `remove` has to enter the
directory to check for uncommitted work, so a missing directory would be an
error. It is not, and that is the problem: git treats "nothing there" as
"nothing to lose", having looked only at the directory.

The consequence for any tool that cleans worktrees: you never need a blanket
prune. Every **live** entry goes through per-path removal. That buys three
things at once. You cannot remove an entry your safety check never examined,
because there is no second code path. One unsafe entry no longer blocks cleanup
of the safe ones, because a withhold is per entry. And your report of what was
removed is a record rather than an assumption, because you removed them one at
a time and watched each result. Stale entries stay out of that loop entirely.

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
