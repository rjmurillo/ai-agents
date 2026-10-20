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

A section is stale when `refs/heads/<name>` does not exist and no checkout
`HEAD` names that branch. The script reads branches with `git for-each-ref`, so
loose refs, packed refs, and reftable all count. The `HEAD` of the main checkout
and of every linked worktree is checked, so an unborn branch keeps its
settings. It never touches
`branch.*` keys without a subsection, such as `branch.autoSetupMerge`.

`--apply` takes a lock file, copies `config` to `config.before-prune` (with a
numeric suffix when that exists), runs `git config --remove-section` for each
stale branch, and checks that git still parses the config.

The lock is `config.prune-lock`, beside `config`. It keeps two `--apply` runs
apart. It does not stop `git branch --track` or `git config`, which never check
it. The stale set is computed again under the lock. A normal exit removes the
lock. A prune that was killed leaves it behind, and the next `--apply` exits `3`
and names the file. Remove `config.prune-lock` once no prune is running.

On any failure, including an interrupt, only the sections this run removed are
written back from the backup, so a concurrent `git config` write to another
section survives. When the live config no longer parses, the whole backup is
copied back instead. When the section restore fails on a config git can still
read, the live file is left in place and the error names the backup.

Exit codes: `0` success (including nothing to prune, a dry-run report, and a
successful `--apply`), `1` stale sections remain and `--fail-on-stale` was
passed, `2` not a git repository, `3` git failed or timed out, or another prune
holds `config.prune-lock`.

## Periodic report

The `branch-config-prune-report` job in the `pre-push` hook of `lefthook.yml`
runs the script with `--fail-on-stale` through
`scripts/ci/report_advisory_result.py`. A push with stale sections prints a
`FAIL advisory.findings` line and a warning. The job never blocks a push and
never writes. Run the script with `--apply` to remove the sections.
