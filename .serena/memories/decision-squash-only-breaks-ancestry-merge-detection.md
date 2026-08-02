# Decision: merge detection cannot use ancestry in this repository

## Question

How does a tool decide whether a branch has already been merged into `main`, so it
can reclaim the branch, its worktree, or its artifacts?

## Conventional answer

Ask git. `git merge-base --is-ancestor <branch> origin/main`, or equivalently
`git branch --merged origin/main`. This is the textbook test, it is what every
cleanup script reaches for, and it needs no network.

## First-principles position

It returns false for every merged branch here, permanently.

`rjmurillo/ai-agents` permits squash merges only:

```
$ gh api repos/rjmurillo/ai-agents --jq '"squash=\(.allow_squash_merge) merge=\(.allow_merge_commit) rebase=\(.allow_rebase_merge)"'
squash=true merge=false rebase=false
```

A squash merge replays the branch as one new commit with a new hash. The original
tips are never reachable from `main`, so ancestry is not merely imprecise for
merged branches, it is inverted for all of them. A test that answers "no" for
every member of the population it exists to detect is worse than no test, because
its output reads as a positive statement about the branch rather than as an
absence of information.

## Evidence

`scripts/maintenance/gc_worktrees.py` used this test, and it is wired into
pre-push as `worktree-gc-report` (`lefthook.yml:375`, merged PR #4214). Measured
2026-08-02 across 184 live worktrees: 60 were retained with the reason
`unpushed commits and not merged to base`. Cross-referencing those 60 branches
against merged pull requests:

```
worktree branches whose PR IS MERGED: 48
not merged / no PR:                   12
```

80 percent of the branches the tool described as unmerged were merged and closed.
A further 53 worktrees were retained as `detached HEAD (no branch to evaluate)`,
of which 8 were clean and already ancestors of `origin/main`. Together 56 of 184,
about 30 percent, were held by a merge test that cannot work here. Filed as issue
\#4255.

## Decision

Do not use ancestry to answer "is this merged" in this repository. Two signals do
work:

1. `delete_branch_on_merge` is `true`, so a squash merge deletes the head branch.
   A branch with a recorded upstream that no longer appears in
   `git ls-remote --heads origin` was merged. One network round trip covers every
   branch in a run; never call it per branch.
2. The pull request state itself, via `gh pr list --state merged --json headRefName`.

Keep ancestry as a cheap first pass. When it says merged it is still right and it
costs nothing. Only its negative answer is uninformative, so never treat that
negative as evidence of unmerged work.

Related but distinct: `.serena/memories/git/git-merge-driver-github-disagreement.md`
uses `--is-ancestor "$BASE" "$HEAD"` to ask whether a PR branch is current with its
base. That is a different question and it remains correct.
