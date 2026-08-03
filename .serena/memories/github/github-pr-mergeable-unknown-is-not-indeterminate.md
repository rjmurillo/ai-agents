# `mergeable: UNKNOWN` is not indeterminate, it is uncomputed

## The finding

The GitHub API field `mergeable` (and `mergeStateStatus`) returns `UNKNOWN` when
GitHub has not yet run its background mergeability job for that pull request. It
does not mean the answer is unknowable. Git can answer it locally in seconds.

On 2026-08-02 sixteen open PRs in this repository returned `UNKNOWN` for both
fields across repeated queries, minutes apart, while other PRs in the same query
returned `MERGEABLE` and `CONFLICTING` normally. The natural reading was that
those sixteen were fine and GitHub just needed a moment.

All sixteen were CONFLICTING.

## The measurement

```bash
git fetch -q origin
MAIN=$(git rev-parse origin/main)
BR=$(gh pr view <N> --json headRefOid --jq .headRefOid)
git cat-file -e "$BR" 2>/dev/null || git fetch -q origin "pull/<N>/head"
git merge-tree --write-tree "$MAIN" "$BR" >/dev/null 2>&1
# exit 0 = merges clean, non-zero = conflicts
```

`git merge-tree --write-tree` performs a real three-way merge into the object
store without touching the working tree, index, or HEAD. It is safe to run from
the main checkout while other worktrees are mid-operation, and it costs under a
second per PR.

Results against main `77e305c6e`, conflicted-file counts:

```
3979 6   3984 3   4005 3   4009 5
4078 15  4095 4   4101 2   4105 1
4109 2   4110 5   4111 3   4113 6
4117 6   4136 4   4164 5   4165 3
```

Sixteen of sixteen. Combined with the thirteen already reported CONFLICTING,
twenty-nine of thirty-eight open PRs conflicted with main at that moment.

## Why the conventional reading is wrong

The conventional handling of `UNKNOWN` is to retry the API until it resolves.
That is correct advice on a quiet repository, where the background job settles in
seconds. It fails here for a structural reason: mergeability is computed against
a moving target. Every merge to main invalidates the cached answer for every
open PR. On a repository merging faster than the job drains, a PR can sit at
`UNKNOWN` indefinitely, and the backlog correlates with exactly the condition
that makes conflicts likely. So `UNKNOWN` is weak evidence FOR conflict, not the
absence of evidence it appears to be.

Waiting also has an asymmetric cost. Polling costs API calls and wall time and
may never resolve. Measuring locally costs one second and is authoritative,
because git is the same merge algorithm GitHub runs.

## Rule

Never treat `mergeable: UNKNOWN` as "probably fine" and never poll it in a loop.
Measure with `git merge-tree --write-tree` and act on the result. Reserve the API
field for the `MERGEABLE` and `CONFLICTING` cases where it has already answered.

## Related

- `.serena/memories/git/git-worktree-tmp-not-durable.md`
- `~/src/scratch/prstat.py` computes required-check readiness; it deliberately
  does not consult `mergeable`, for the reason above.
