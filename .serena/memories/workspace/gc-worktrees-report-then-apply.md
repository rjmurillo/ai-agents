# `gc_worktrees.py`: report first, and read the rescue chain it prints

## Report mode before `--apply`

`scripts/maintenance/gc_worktrees.py` in report mode (`--json`, no `--apply`)
classified 16 of 42 registered worktrees as safely removable ("fully pushed").
`--apply` then removed exactly those 16 and nothing else. Measured 2026-08-27.

`--apply` deletes worktrees. That is its job, not a side effect. The measured
result is that the set it removed matched the set the report named.

## The rescue command is not optional bookkeeping

For an entry reported as "would have removed, but its admin directory is the
only anchor for work", the tool prints a `git -C <repo> branch gc-rescue-<sha>
<sha>` chain. Run it.

That warning cannot fire for a commit that is already safe. `_admin_warning`
in `scripts/maintenance/_gc_reasons.py` builds it from
`unreachable_admin_commits`, so every SHA it names is unreachable from ordinary
refs by construction. A SHA already on an origin ref would be reachable and
would produce no warning at all, so "the rescue branch is redundant once the
SHA is on origin" describes a case this message never covers.

## The printed chain is a prefix, not the whole list

One branch rescues one SHA, and `_admin_warning` emits commands for
`orphans[:3]` only. Past three it appends a count of the rest plus the admin
path that names them, with no command for them.

So when that count appears, do not remove the entry. Rescue the first three
from the chain, then read the remaining SHAs out of the admin directory the
message names and branch them too. Removing while the count is non-zero loses
commit four onward, because the removal deletes the directory that named them.

## Do not remove by hand after the report

A report is a snapshot. Between it and the removal, a worktree can go dirty, a
commit can land, or another agent can start work in it. After the rescue
branches exist, rerun this tool in report mode and then with `--apply`, so its
freshness and safety checks govern the removal, rather than calling
`git worktree remove --force` directly against a stale verdict.

## Related

- [workspace-shared-checkout-is-a-stale-detached-head](workspace-shared-checkout-is-a-stale-detached-head.md).
  A different way a worktree's recorded state misleads you.
