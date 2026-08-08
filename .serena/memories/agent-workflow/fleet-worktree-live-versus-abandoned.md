# Fleet Worktrees: Live Versus Abandoned

**Last Updated**: 2026-08-04
**Source**: Session measurement, overturn #169

## Constraint (HIGH confidence)

A dirty worktree does **not** mean an agent is working in it. The agent fleet is
not durable state: the runtime wiped a 32-agent fleet mid-session and left every
worktree behind. A dirty worktree proves someone once started, not that anyone is
working now.

An ownership check that treats "dirty" as "owned" permanently freezes every issue
whose worktree was orphaned by a wipe. Measured cost when this rule was broadcast
to the fleet: two agents stood down and shipped nothing across 1598 seconds of
combined runtime, on issues nobody was working.

## The discriminator is age, not the directory name

A worktree is LIVE only if its newest file touch is under roughly 60 minutes old.
Anything older with uncommitted edits or unpushed commits is ABANDONED, and it
should be harvested rather than avoided.

```bash
newest=$(find "$p" -path '*/.git' -prune -o -type f -printf '%T@\n' | sort -rn | head -1)
python3 -c "import time,sys; print(int((time.time()-float(sys.argv[1]))/60))" "$newest"
```

**Do not match directory basenames against dispatched agent names.** That fails in
both directions, and the false-LIVE direction is the expensive one. An abandoned
`ai-agents-mergerace-3483113` (263 minutes stale) reads as the live agent
`mergerace` because the basename carries a numeric collision suffix. Acting on
that name match froze the review-thread cluster a second time, and the retraction
had to go out ten minutes after the original correction. The live `mergerace`
worktree held `scripts/ci/ruff_ratchet.py`; the abandoned one held the
review-thread files. Only the file list settled it.

Confirm with the file list, not the age alone: `git -C "$p" status --porcelain`
tells you whether the worktree holds the specific file you need.

## Do not over-claim the size of the graveyard

`git rev-list --count origin/main..HEAD` overstates unlanded work badly in a
squash-merge repo, because a squash-merged branch still reports every one of its
original commits as "ahead". Measured on stale worktrees: one reported 56 commits
ahead and 329 changed files, of which only 11 still differed from `main`. Another
reported 255 changed files with 7 still differing.

`git ls-remote` returning nothing is also not proof, since GitHub deletes head
branches after merge.

The usable test is whether the branch's own changed files still differ from
`main`:

```bash
own=$(git -C "$p" diff origin/main...HEAD --name-only)
git -C "$p" diff origin/main HEAD --name-only -- $own | wc -l
```

That is still an upper bound, because it also counts files `main` moved forward
on its own. Treat it as a triage signal, never as a finding.

## At fleet scale, join against pull request state

The age and file-list checks above answer one worktree at a time. Across 185
worktrees they are too slow, and every cheap test fails in the same direction:
this repository squash-merges and deletes the head branch, so a branch whose
work landed is not an ancestor of `main` and its remote ref is gone. Landed work
answers both questions exactly the way lost work does. Measured: 125 of 185
worktrees matched "not on main, no remote branch", while about 9 held work that
was never proposed.

One API call classifies the current fleet against the most recent 1,000 pull
requests:

```bash
gh pr list --state all --limit 1000 --json number,state,headRefName,headRefOid
```

Join that against the worktree list by branch name. Three populations fall out.
All three can hold work absent from `main`: a detached tip can carry
unreferenced commits, and a merged-head worktree can carry commits made after
the merge, per `.serena/memories/quality/verify-squash-merge-by-content-not-ancestry.md:85-87`.
The PR join changes triage priority, not certainty.

| Population | Measured count | Verdict |
|---|---|---|
| Detached checkout, no branch | 50 | Review leftovers; confirm reachability (`git for-each-ref --contains "$sha"`, see `.serena/memories/git/git-a-worktree-whose-directory-is-gone-can-still-be-removed-by-path.md:123-126`) before removal, not automatically disposable |
| Branch is head of a MERGED pull request | 23 | Landed; anchor its tip before disposal, since a merged head can still carry a later stranded commit |
| Named branch, no pull request in fetched set | 52 | Highest-priority triage; most likely to hold lost work |

If a branch appears in more than one pull request, classify it by the set of
states and let MERGED win, but only when the merged pull request's `headRefOid`
matches the worktree's current tip. State alone can misclassify a reused head
name: an older merged PR, a newer open PR, and a local post-merge tip can share
one branch name, and fork PRs can collide on `headRefName` too. Request
`headRefOid` in the same query and treat a current tip that does not match the
merged PR's recorded OID as requiring individual triage instead of letting the
older MERGED row win.

Sort that third group by **commit date, not commit count**. Fifteen commits from
February is dead. Two commits from Tuesday is a forgotten pull request. Sorting
by count puts the dead branches on top and buries the recoverable ones. Paginate
the pull request query before treating absence from the fetched set as proof that
no pull request exists.

Measured yield: four of the 52 were clean and under a week old. Two of those
four fixed a byte budget the fleet had been failing against for five days.

## Anchor unreachable tips before removing anything

Removing a worktree drops its tip when nothing else references it. Create two
independent anchors first. Both are cheap.

```bash
git update-ref "refs/salvage/<nnn>-<branch-slug>" "$sha"   # once per tip
git bundle create ~/src/scratch/tips.bundle --stdin        # feed it ref NAMES
git bundle verify ~/src/scratch/tips.bundle
```

`git bundle create` refuses a list of bare SHAs with `Refusing to create empty
bundle`, so `update-ref` is a prerequisite and not an optional extra. The refs
survive `git gc` and live in the canonical repository, where a worktree prune
cannot orphan them. The bundle survives losing the repository. Measured: 136
unreachable tips, 107 MB, a few minutes.

## Rule

Before standing down on an issue because a worktree looks owned, measure the age
and list the files. Harvest abandoned work on merit: it is unreviewed, unproven,
and frequently wrong, so keep only what you verify independently and say what you
discarded.
