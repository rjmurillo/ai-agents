# Branch-context exemption keys on upstream presence, not recency

## Question

`check_branch_context` in `scripts/validation/git_hook_policy.py` picks the
session log by recency alone. A `git merge origin/main` imports the previously
merged branch's log, which is newer than anything the feature branch owns, so
the branch mismatch fires forever and the branch cannot be pushed.

## Conventional answer

The function already exempted merges, keyed on `_merge_in_progress`
(tests for `MERGE_HEAD`). Git deletes `MERGE_HEAD` when the merge commit is
created, so the exemption covers the seconds of conflict resolution and expires
exactly when the imported log becomes permanent. The window is inverted.

## First attempt that was wrong

Exempt whenever the branch owns a recent log of its own. That broke three
existing tests, and those tests were right: being on a branch you initialized
does not mean you did not session-init on another branch five minutes ago.
That is the live issue #682 co-mingling signal the guard exists to catch.

## The discriminator that works

Upstream presence. A log that already exists on `origin/HEAD`'s branch is
settled history, not a claim about current work. A log authored on another
local branch is not upstream. `_is_merged_history` resolves
`git rev-parse --abbrev-ref origin/HEAD`, then `git cat-file -e <upstream>:<relpath>`,
and fails closed on any indeterminate input. The exemption now requires BOTH
that the branch owns a recent log AND that the newest log is upstream.

All three recency tests survive unchanged, which is the evidence the guard was
narrowed rather than weakened.

## Also worth knowing

The old behavior was nondeterministic, not merely wrong. `git checkout`
rewrites mtimes as it materializes files, so whichever session log git writes
last wins the recency comparison. Both outcomes were measured on the same
branch at the same commit one minute apart. A flaky gate is worse than an
always-blocking one: it gets disabled rather than fixed.

## Decision

Shipped in PR #3344 (issue #3343). Tests live in
`tests/test_lefthook_integration.py`; the `_add_upstream_with` helper builds a
bare clone as `origin` and sets `refs/remotes/origin/HEAD` so the upstream
lookup has something real to resolve.
