# A shallow graft is repository-global, so one `--depth` fetch blocks every push

## The trap

`git fetch --depth=<n>` writes a `shallow` file into the **common** git
directory. Linked worktrees do not get their own. Every worktree of this
repository then reports `rev-parse --is-shallow-repository` as `true`, and
`push-ref-policy` refuses the push with exit 2 in all of them at once.

The fetch that caused it is usually not in the worktree you are standing in.
Reproducing a CI step locally is the common source, because several jobs
historically fetched with `--depth=1`.

## What it looks like when it bites

Observed 2026-08-04. A push from `wt-shallowfix` was refused:

```
ERROR: push validation requires complete Git history.
  A `git fetch --depth=<n>` made this clone shallow, most likely while
  reproducing a CI step locally.
  Fix: git fetch --unshallow origin
```

Nothing in that worktree had run a depth-limited fetch. The graft lived in the
primary clone's `.git/shallow`, pinned at `81a2a7469`, and had already blocked
every other worktree silently, since none of them had tried to push yet.

Confirm the shape rather than guessing:

```bash
git rev-parse --git-dir          # .git/worktrees/<name>  in a linked worktree
git rev-parse --git-common-dir   # .git                   shared by all of them
cat "$(git rev-parse --git-common-dir)/shallow"
```

## Do this instead

Repair once, from any worktree:

```bash
git fetch --unshallow origin
```

Verified 2026-08-04: a single `--unshallow` from the primary clone flipped four
worktrees (`ai-agents`, `wt-covgap`, `wt-doctrinefix`, `wt-e2eauth`) to
`is-shallow=false` simultaneously and removed the shared `shallow` file. The
sharing runs in both directions: one graft blocks the fleet, one repair clears
it.

Never hand-delete `shallow`. The file is what tells git which commits have
truncated parents; removing it leaves the object store still missing those
parents and produces corruption reports instead of a clean history.

An ordinary undepthed `git fetch` does **not** clear an existing graft. Only
`--unshallow` (or `--depth` large enough to reach the roots) does.

## Why the diagnostic used to go missing

Until issue #4576, the guard looked for `repo_root / ".git" / "shallow"`. In a
linked worktree `<root>/.git` is a pointer file, so that path named a child of a
file, never existed, and the line naming the pinning SHA was dropped. The guard
still blocked; it just stopped saying where the graft was, in exactly the
multi-worktree layout where that is hardest to work out by hand.

The fix asks git for the path (`rev-parse --git-path shallow`) rather than
building it. Git already knows which files are shared across worktrees and which
are per-worktree, so it routes `shallow` to the common directory on its own:

```
$ cd <a linked worktree> && git rev-parse --git-path shallow
/home/you/src/primary/.git/shallow
```

That is also the idiom `_check_no_grafts` uses 30 lines above, with
`--git-path info/grafts`. Parsing the pointer file by hand would have needed
shape-specific logic, since a submodule's `.git` points at `.git/modules/<name>`
and that path *is* its common directory, not its grandparent.

The sharing is contractual, not an accident of one git build.
`gitrepository-layout(5)` says of `shallow`: "This file is ignored if
`$GIT_COMMON_DIR` is set and `$GIT_COMMON_DIR/shallow` will be used instead."
It also names `info/grafts` as the sibling mechanism, which is why the same
idiom fits both. `git-worktree(5)` gives the matching directive: "To access
refs, it's best not to look inside `$GIT_DIR` directly. Instead use commands
such as git-rev-parse(1)." So the rule generalizes past `shallow`: when you
need a path under the git directory, ask `rev-parse --git-path` for it instead
of joining `.git` yourself, and the worktree, submodule, and
`$GIT_OBJECT_DIRECTORY` cases all resolve without shape-specific code.

## Related

`.serena/memories/git/git-stash-is-shared-across-every-worktree.md` is the same
family: the stash stack also lives in the common directory, so a concurrent
agent's `stash push` and your `stash pop` share one stack.

A graft has a CI-side consequence too: it makes `git merge-base` return nothing
for the rest of the job, which fails one ratchet closed and another open. That
is documented in `decision-shallow-fetch-kills-merge-base-in-ci.md`, which ships
with PR #4572 and is not on `main` until that lands.
