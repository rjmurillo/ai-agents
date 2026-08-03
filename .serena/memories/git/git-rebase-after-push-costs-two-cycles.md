# Rebasing a Branch You Already Pushed Costs Two Push Cycles

**Category**: Git Operations
**Source**: 2026-08-03, branch `docs/memory-markdownlint-empty-scope`. Verified on git 2.43.0, lefthook pre-push, `detect_scope_explosion.py` at `15ce43fad`.

Symptom this explains: `! [rejected] ... (non-fast-forward)` after a pre-push run
that already spent about 17 minutes, followed by a `BLOCKED: PR scope explosion`
commit refusal on a change of one file.

## Statement

`git rebase origin/main` on a published branch that is not already based on
`origin/main` rewrites the published tip, so the next push is a non-fast-forward
and is rejected. When the branch is already linearly based on the target, rebase
is a no-op and this whole memory does not apply.

The rejection arrives **after** the pre-push hook group completes. The cause is
not that the hook runs before git contacts the remote; it does not. Git fetches
the remote's advertised refs, classifies the non-fast-forward on the client,
runs `pre-push` anyway, and only then reports the rejection.

The consequence is the part worth remembering: git **omits the already-rejected
ref from the hook's stdin**, so the hook is handed an empty ref list. No
pre-push hook can detect this case and short-circuit, because git never tells it
which push is doomed. The suite is the long pole at roughly 1000 seconds, and it
is spent in full on a push that was decided before it started.

Reproduced on git 2.43.0 with a bare local remote, an amended tip, and a
`pre-push` hook that appends its stdin to a file. The hook logged its run marker
and an empty stdin between the start and end markers, and the push then failed
with `Updates were rejected`:

| observation | result |
|---|---|
| hook invoked on a doomed push | yes |
| refs on hook stdin | none |
| rejection reported | after the hook exited |

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

Ask whether the branch is published before rebasing it. Ask the remote, not a
remote-tracking ref:

```bash
branch=$(git symbolic-ref --quiet --short HEAD) || {
  echo "detached HEAD: finish or abort the rebase before asking this question"; }
git ls-remote --exit-code --heads \
  "$(git config --get "branch.$branch.remote" || echo origin)" "$branch"
```

Exit 0 means the branch is published, so integrate with `git merge` rather than
`git rebase`. Exit 2 means it is not published and a rebase is free.

The obvious one-liner, `git rev-parse --verify --quiet
"origin/$(git branch --show-current)"`, is wrong in three ways, and each failure
returns empty, which reads as "local only, rebase is free":

- **Detached HEAD prints nothing**, so the lookup becomes `origin/` and fails.
  This is not hypothetical: a conflicted rebase leaves you detached, which is
  exactly the state in which you are most likely to be asking. Worse, a `| tail`
  anywhere in the command chain masks the rebase's non-zero exit, so a following
  `&&` still fires and pushes from that detached state. Use `${PIPESTATUS[0]}`
  or `set -o pipefail` in any chain that gates a push.
- **A triangular workflow may push elsewhere.** The push destination is
  `branch.<name>.remote`, which need not be `origin`.
- **A stale remote-tracking ref reports published when it is not**, unless the
  fetch pruned. This checkout sets `fetch.prune=true`; that is local
  configuration, not a property of the command.

`git ls-remote` costs one round trip and has none of these failure modes.
Against a 1000-second hook run, the round trip is free.

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
