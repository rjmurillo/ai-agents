# Verify a squash-merged branch by content, not by ancestry

## The claim this overturns

"My branch merged, so its commits are ancestors of `origin/main`." False in this
repository. `rjmurillo/ai-agents` merges pull requests by squash. A squash
rewrites the branch into one new commit with a new parent, so none of the
original commit objects ever become reachable from `main`.

`git merge-base --is-ancestor <sha> origin/main` therefore returns non-zero for
every commit on a branch that merged successfully. Reading that as "the merge
did not land" is a false negative, and it is guaranteed rather than occasional.

## What to run instead

Ask whether the content arrived, not whether the commit did.

```bash
git fetch origin main --quiet
git cat-file -e origin/main:path/to/file && echo PRESENT || echo ABSENT
git show origin/main:path/to/index.md | grep -c 'the-row-you-added'
```

For a whole change, diff the paths you touched against `origin/main` and expect
an empty diff. The squash commit's subject line usually carries the PR number,
so `git log origin/main --oneline -5` confirms which PR produced it.

## The second trap: the merge deletes the branch under you

Repository settings delete the head branch on merge. A local commit created
after the merge lands has no remote branch to push to. The push does not fail
with a rejection, which is what a stale-branch failure looks like. It fails with
an absent ref:

```
PUSH_RC=1
LOCAL=c01ac3bb38a3a8aae7a59234409bbb2a40ce1813
REMOTE=ABSENT
VERIFIED=no
```

`REMOTE=ABSENT` after a push attempt means one of two things, and they need
opposite responses:

- The branch was never pushed. Push it.
- The branch was pushed, merged, and reaped. The commit is stranded. Rebase it
  onto fresh `origin/main` on a new branch and open a second pull request.

Distinguish them by checking whether the earlier commits' content is on `main`.
If it is, the branch was reaped and you are in the second case.

## Why this is easy to get wrong

Both failure modes present as "the thing I did is not on the remote," and both
of the obvious verification commands lie in the same direction:

- `--is-ancestor` says NO for a successful squash merge.
- `git ls-remote origin refs/heads/<branch>` exits 0 with empty output for a
  deleted branch, so a naive `RC` check reads as success.

Combining them produces a confident, wrong conclusion that the work was lost.
The content check is the only one that answers the question actually being
asked.

## Worked instance

Pull request #4603 squash-merged as `95ecfc3e9c`. Three local commits reported
`ancestor-of-main: NO`, yet
`.serena/memories/quality/add-missing-state-not-sentinel.md`,
`scripts/ci/memory_index_token_ratchet.py`, and
`scripts/update_memory_index_tokens.py` were all present on `main`. The cluster
had landed. One later commit, made after the merge completed, was stranded and
had to be replayed onto a fresh branch.

## The content check does not scale to a fleet

The content check above costs a `git diff` per branch. Across 185 worktrees that
is too slow, and it asks a question the pull request API already answers in one
call:

```bash
gh pr list --state all --limit 1000 --json number,state,headRefName
```

A branch that is the head of a MERGED pull request landed, whatever ancestry
says, but it can still carry a later stranded commit. Anchor the current tip
before disposal. A branch absent from the fetched pull request set is the group
most likely to hold lost work. Reach for the per-file content check inside that
group, not across the whole fleet.

## Related

- `.serena/memories/agent-workflow/fleet-worktree-live-versus-abandoned.md`. The
  population split behind that one API call, and the procedure for anchoring
  unreachable tips before a worktree is removed.
- `.serena/memories/quality/add-missing-state-not-sentinel.md`. The same defect
  shape: a two-valued answer used where the question has three outcomes
  (present, absent, cannot determine).
