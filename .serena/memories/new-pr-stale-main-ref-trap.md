# new_pr.py fails opaquely when the local `main` ref is stale

## Symptom

`.claude/skills/github/scripts/pr/new_pr.py` exits 1 after printing only:

```
Session End validation failed
Preparing to create PR: <branch> -> main
...
[1/6] Checking Session End protocol...
```

No further detail. The session log on the branch validates clean when you run
`scripts/validate_session_json.py` against it by hand, which makes the failure
look like a validator bug.

## Cause

The script computes its changed-file set with `git diff --name-only <base>...<head>`
(`new_pr.py:282`) and `--base` defaults to the bare string `main`
(`new_pr.py:519`), so the diff resolves the **local** `main` ref, not
`origin/main`. In a long-lived worktree the local `main` ref is never updated by
ordinary work, so it drifts arbitrarily far behind. Two dated observations:
local `main` at `a65181a264` against `origin/main` at `769c21c37b` on
2026-08-02 morning; local `main` at `ede9fd1fe` two commits behind `origin/main`
at `5ee7a95d5` the same evening. Neither number is reproducible later; the
mechanism is, because nothing in the loop advances the local ref.

Passing `--base origin/main` does not work around it. The same value is handed
to `gh pr create --base` (`new_pr.py:605-606`), which needs a branch name.

In the 2026-08-02 morning episode the consequence was a changed-file set wrong
by two orders of magnitude:

| local `main` | files reported by `main...head` |
|---|---|
| stale `a65181a264` | 1515 |
| refreshed `da88c2e923` | 14 |

Every `.agents/sessions/*.json` that landed on `main` since the drift began is
swept into the set. The Session End check then picks the newest of those
hundreds of unrelated logs and validates it instead of the branch's own log.

## Detect

Refresh the remote-tracking ref, which is always safe from any worktree, then
ask the refs themselves how far apart they are:

```bash
git fetch origin main
git rev-list --left-right --count main...origin/main
```

That is the authoritative signal and the only one that settles the question, but
it has to be read by direction, not as a single "are they different" number. For
`A...B` the left field counts commits reachable from `A` and not from `B`, and
the right field counts commits reachable from `B` and not from `A`. So for
`main...origin/main` the left field is how far local `main` is **ahead** of
`origin/main`, and the right field is how far local `main` is **behind** it.
Only a non-zero right field is the stale ref that `new_pr.py` diffs against.

Four cases, with what the fast-forward in the next section actually does in
each. Verified against git 2.43.0:

| left | right | state of local `main` | `git merge --ff-only origin/main` |
|---|---|---|---|
| `0` | `0` | equal, ref is current | prints `Already up to date.`, exits 0, nothing to do |
| `0` | `>0` | behind only, the trap this memory is about | fast-forwards, exits 0, refs equal afterward |
| `>0` | `0` | ahead only, **not** stale-behind | prints `Already up to date.`, exits 0, and **leaves the refs unequal** |
| `>0` | `>0` | diverged | prints `fatal: Not possible to fast-forward, aborting.`, exits 128, touches no ref |

The ahead-only row is the one that misleads. `--ff-only` does not refuse there.
It succeeds, reports there is nothing to do, and leaves `main` pointing exactly
where it did, so a zero exit status from the merge is not evidence that the refs
now agree. Compare the refs, never the exit status.

Treat both `left > 0` rows as stop and escalate. Local `main` holds commits that
`origin/main` does not, so reconciling it is a deliberate branch policy decision
(push those commits, move them onto a branch, or discard them knowingly), not a
ref refresh. Do **not** reach for `reset --hard`, `push --force`, or a rebase of
`main` to drive the counts to `0` and `0`. Those rewrite or destroy commits
whose provenance you have not established, and ahead-only is not the failure
this memory is about in the first place.

Measured in this worktree on 2026-08-02 the command printed `0` then `2`
(tab-separated), the behind-only row, with local `main` at `ede9fd1fe` and
`origin/main` at `5ee7a95d5`.

Do **not** use changed-file counts as the test. `new_pr.py` validates exactly
one log, the newest by `(date, session number)` among the changed
`.agents/sessions/` logs (`new_pr.py:300-317`), so the outcome turns on which
paths are in that subset and which one sorts last. Compare memberships, not
cardinalities:

```bash
diff <(git diff --name-only main...HEAD | grep '^\.agents/sessions/' | sort) \
     <(git diff --name-only origin/main...HEAD | grep '^\.agents/sessions/' | sort)
```

A `wc -l` comparison is not evidence in either direction. On 2026-08-02 in this
worktree `main...HEAD` and `origin/main...HEAD` both returned the same 6 paths,
identical in membership, while `main` sat 2 commits behind: equal counts and a
stale ref at the same time. Earlier the same day the stale set was 1515 paths
against a real 14. A large difference is a symptom worth reading; agreement is
not a clean bill of health.

## Fix

This section covers the behind-only row, `0` left and non-zero right, and only
that row. For the ahead-only and diverged rows nothing here reconciles the refs,
so stop and escalate instead of running any of it.

Fast-forward the local ref. Do **not** reach for `git fetch origin main:main`
from a linked worktree: git refuses to fetch into a branch that is checked out
in *any* worktree of the repository, not just the current one. Run from a linked
worktree on 2026-08-02 it died with exit 128 and never touched a ref:

```console
$ git fetch --dry-run origin main:main
fatal: refusing to fetch into branch 'refs/heads/main' checked out at '<main worktree path>'
```

Fast-forward it from the worktree that has `main` checked out instead, which is
also refuse-on-non-fast-forward and so cannot silently rewrite anything:

```bash
git -C /path/to/main/worktree merge --ff-only origin/main
```

`git fetch origin main:main` is correct only in a clone where `main` is checked
out nowhere. Verify with `git rev-list --left-right --count main...origin/main`
afterward; both fields must read `0`. That count, not the merge's exit status,
is the check: the ahead-only no-op exits 0 as well. Re-running the changed-file
counts is not a post-fix check either: on 2026-08-02 they read 6 versus 6 while
the ref was still 2 commits behind.

## Why this keeps happening

Nothing in the ordinary loop refreshes local `main`. `git fetch origin main`
updates `origin/main` only. Work in a linked worktree never checks `main` out.
So the drift grows silently and the first symptom is an unrelated-looking
validation failure at PR creation time, which is the least informative place to
discover it.

## Related

- Issue #2387. An earlier opaque form of the same message, fixed for the
  missing-file case but not for the stale-ref case.
