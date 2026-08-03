# Rebasing a Branch You Already Pushed Costs Two Push Cycles

**Category**: Git Operations
**Source**: 2026-08-03, branch `docs/memory-markdownlint-empty-scope`. Verified on git 2.43.0, lefthook pre-push, `detect_scope_explosion.py` at `15ce43fad`.

Symptom this explains: `! [rejected] ... (non-fast-forward)` after a pre-push run
that already spent about 17 minutes, followed by a `BLOCKED: PR scope explosion`
commit refusal on a change of one file.

## Statement

`git rebase origin/main` on a branch whose tip is already published rewrites
every commit, so the next push is a non-fast-forward and is rejected. The
rejection arrives **after** the pre-push hook group completes, because lefthook
runs the group before git contacts the remote. The suite is the long pole at
roughly 1000 seconds, so the whole cost is paid before git reports that the push
was never going to land.

Force-pushing is the obvious repair and policy forbids it. The compliant repair
is to merge the remote tip back, which then trips a second defect:
`detect_scope_explosion.py:197-207` treats `MERGE_HEAD` as an upstream being merged in.
That is true for `git merge origin/main` and false for
`git merge origin/<same-branch>`, where the branch's own remote tip is behind
main. The detector then counts everything main gained since that tip.

Measured on a merge whose staged change was one file and whose branch against
main was four:

| measure | value |
|---|---|
| staged files vs `HEAD` | 1 |
| branch vs `origin/main`, three-dot | 4 |
| `detect_scope_explosion.py` report | 98, against a limit of 50 |

Issue #4418 records the identical shape at 635 reported against 17 real.

## Prevention

Ask whether the branch is published before rebasing it. One command, no
network round trip after a fetch:

```bash
git fetch -q origin
git rev-parse --verify --quiet "origin/$(git branch --show-current)"
```

Non-empty output means the branch is published, so integrate with `git merge`
rather than `git rebase`. Empty output means it is local only and a rebase is
free.

## Repair, once you are already in it

1. `git merge origin/<branch>`. Resolve in favour of the local side when the
   local side is the reviewed one; the remote side is the pre-rebase original.
2. The commit will be refused by the scope detector. Confirm the real size
   first, with `git diff --cached --name-only HEAD` and
   `git diff --name-only origin/main...HEAD`, three dots.
3. Only when those two numbers are small, commit with `SKIP_SCOPE_CHECK=1` and
   record both numbers plus issue #4418 in the commit message. Every other hook
   still runs. Skipping the check without stating the measured size turns a
   known false positive into an unaudited bypass.

## Do not

Do not read the detector's number as a reason to split the branch. It is not
measuring your branch. Do not re-run the push hoping the rejection was
transient; a non-fast-forward is a deterministic property of the two histories.

## Related

- `git-merge-preflight.md`. Detect upstream deletions before merging.
- `git-merge-driver-github-disagreement.md`, "Controls that lie". The same
  divergence also misreads as mass deletions under a two-dot
  `git diff origin/main..HEAD`, which is why step 2 above specifies three dots.
