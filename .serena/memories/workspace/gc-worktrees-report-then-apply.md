# `gc_worktrees.py`: report first, and read the rescue chain it prints

## Report mode before `--apply`

`scripts/maintenance/gc_worktrees.py` in report mode (`--json`, no `--apply`)
classified 16 of 42 registered worktrees as safely removable ("fully pushed").
`--apply` then removed exactly those, with zero side effects. Measured
2026-08-27.

## The rescue command is not optional bookkeeping

For an entry reported as "would have removed, but its admin directory is the
only anchor for work", the tool prints a `git -C <repo> branch gc-rescue-<sha>
<sha>` chain to run before `git worktree remove --force <path>`. Run it.

That warning cannot fire for a commit that is already safe. `_admin_warning`
in `scripts/maintenance/_gc_reasons.py` builds it from
`unreachable_admin_commits`, so every SHA it names is unreachable from ordinary
refs by construction. A SHA already on an origin ref would be reachable and
would produce no warning at all, so "the rescue branch is redundant once the
SHA is on origin" describes a case this message never covers.

Read the whole chain, not the first command. One branch rescues one SHA, so the
warning joins up to three of them with `&&`, and when more than three are at
risk it appends a count of the rest with the admin path that names them. Copying
only the first command loses the others when the removal deletes that directory.

## Related

- [workspace-shared-checkout-is-a-stale-detached-head](workspace-shared-checkout-is-a-stale-detached-head.md).
  A different way a worktree's recorded state misleads you.
