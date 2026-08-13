# git status --porcelain is not proof a worktree holds no work

`git status --porcelain` reports the working tree and the index. It does not
report a suspended git operation, and an operation can be suspended with both
of those completely clean.

Reproduced against real git 2.43.0:

```bash
OTHER=$(git commit-tree HEAD^{tree} -p HEAD -m orphan)
git merge --no-commit --no-ff "$OTHER"
git status --porcelain    # empty
git rev-parse MERGE_HEAD  # the commit, reachable from nothing else
```

The merge produces no tree change, so porcelain is silent. HEAD has not moved,
so a HEAD comparison passes. `commit-tree` writes no reflog entry, so a reflog
probe finds nothing. The only anchor is `MERGE_HEAD`, which lives in the
worktree's own admin directory (`.git/worktrees/<name>/`). Deleting the
worktree deletes the anchor and orphans the commit. `git fsck --unreachable`
confirms it afterwards.

`git worktree remove` does not guard this. Neither does it guard `index.lock`:
verified that it removes a worktree whose index another process is holding,
exits 0, and prints nothing.

The full set of per-worktree markers worth checking: `MERGE_HEAD`,
`CHERRY_PICK_HEAD`, `REVERT_HEAD`, `BISECT_LOG`, `rebase-merge/`,
`rebase-apply/`, `sequencer/`, `index.lock`.

Resolve the admin directory from the checkout's own `.git` marker file
(`gitdir: <path>`), not by scanning registered entries. Two file reads, no
subprocess. See `admin_dir_from_marker` and `in_progress_operation` in
`scripts/maintenance/_gc_stale.py`.

Five adversarial review rounds missed this. The sixth found it because it
asked what git records that `status` does not print.
