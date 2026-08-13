# A newline in a worktree path splits porcelain, and that fails safe

`git worktree list --porcelain` does not quote paths. A worktree whose path
contains a newline emits a record split across two lines, and a naive parser
reads the text before the newline as the whole path.

Verified on git 2.43.0:

```
$ git worktree add --detach "$(printf 'wt\nnewline')"
$ git worktree list --porcelain
worktree /repo/wt
newline
HEAD 2ad25908...
detached
```

`git help worktree` names `-z` as the fix: "Terminate each line with a NUL
rather than a newline when --porcelain is specified with list. This makes it
possible to parse the output when a worktree path contains a newline
character."

## Why `scripts/maintenance/_gc_parse.py` still does not pass `-z`

Both reachable constructions were built and run against the real tool. Neither
loses a commit.

**Two worktrees, `wt` and `wt\nnewline`.** Both records parse to `/repo/wt`, so
the tool evaluates `wt`'s cleanliness twice and both decisions carry the path
`/repo/wt`. Removal targets `/repo/wt`, which git resolves to the real `wt`
exactly. A commit stranded in `wt\nnewline`'s reflog survives, because that
worktree is never the removal target. Confirmed: an abandoned commit made in
`wt\nnewline` was still in the odb after the pass.

**Only `wt\nnewline`.** The truncated path has no admin entry, so the tool
refuses before checking anything else:

```
'/repo/wt' remove= False | could not locate its admin entry, so nothing
else about it was checked; stale admin entry
```

The misparse therefore costs a wasted decision, never a removal of the wrong
worktree. Adding `-z` would change the option set the tool requires from git
to fix a hazard that no construction turns into loss, so the version risk is
not worth taking on evidence this thin.

If a construction is ever found where the misparse does remove the wrong
worktree, `-z` is the fix and this note is the reason it was deferred.

Refs: issue #2761, branch `fix/gc-worktrees-stale-entries`.
