# Stale branch sections in .git/config

Issue #5360 tracks unbounded growth of `[branch "<name>"]` sections in the
shared `.git/config`. Git adds a section when a branch gets an upstream and
never removes it when the branch is deleted. One incident measured 44648 bytes
and 416 sections. A later measurement found 55496 bytes and 1033 `branch.*`
keys against 781 local branches.

## Prune

```bash
uv run --frozen python scripts/maintenance/prune_branch_config.py          # report only
uv run --frozen python scripts/maintenance/prune_branch_config.py --apply  # remove
```

A section is stale when `refs/heads/<name>` does not exist. The script reads
branches with `git for-each-ref`, so loose refs, packed refs, and reftable all
count. It keeps the branch that `HEAD` names in the main checkout and every
linked worktree, so an unborn branch keeps its settings. It never touches
`branch.*` keys without a subsection, such as `branch.autoSetupMerge`.

`--apply` copies `config` to `config.before-prune` (with a numeric suffix when
that exists), runs `git config --remove-section` for each stale branch, and
checks that git still parses the config. On any failure it restores the copy.

Exit codes: `0` success or dry run, `2` not a git repository, `3` git failed.
