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
using the **local** `main` ref, not `origin/main`. In a long-lived worktree the
local `main` ref is never updated by ordinary work, so it drifts arbitrarily far
behind. Observed on 2026-08-02: local `main` at `a65181a264` against `origin/main`
at `769c21c37b`.

The consequence is a changed-file set that is wrong by two orders of magnitude:

| local `main` | files reported by `main...head` |
|---|---|
| stale `a65181a264` | 1515 |
| refreshed `da88c2e923` | 14 |

Every `.agents/sessions/*.json` that landed on `main` since the drift began is
swept into the set. The Session End check then picks the newest of those
hundreds of unrelated logs and validates it instead of the branch's own log.

## Fix

Fast-forward the local ref before creating the PR. This works from a worktree
where `main` is not checked out, and refuses a non fast-forward, so it cannot
silently rewrite anything:

```bash
git fetch origin main:main
```

Confirm the set is sane before retrying:

```bash
git diff --name-only main...HEAD | wc -l
```

If that count is far larger than the branch's real diff, the ref is still stale.

## Why this keeps happening

Nothing in the ordinary loop refreshes local `main`. `git fetch origin main`
updates `origin/main` only. Work in a linked worktree never checks `main` out.
So the drift grows silently and the first symptom is an unrelated-looking
validation failure at PR creation time, which is the least informative place to
discover it.

## Related

- Issue #2387. An earlier opaque form of the same message, fixed for the
  missing-file case but not for the stale-ref case.
