# A Squash Merge Severs a Stacked Pull Request

**Category**: Git Operations
**Source**: 2026-08-06, PR #4708 and PR #4718. Verified on git 2.43.0
against `origin/fix/worktree-walk-timeouts`,
`origin/fix/gc-worktrees-one-decision`, and
`origin/fix/gc-worktrees-stale-entries`. GitHub recorded
`automatic_base_change_succeeded` at 2026-08-07T00:15:48Z.

Symptom this explains: merging a new base into a stacked child reports 17
conflicts, including 11 `add/add` conflicts, on paths inherited through the
stack.

## Statement

The stack was:

```text
main
  fix/worktree-walk-timeouts
    fix/gc-worktrees-one-decision
      fix/gc-worktrees-stale-entries
```

PR #4708 squash-merged `fix/gc-worktrees-one-decision` into
`fix/worktree-walk-timeouts` as `0d386e7a5`. A squash commit copies content
onto a brand-new commit. It does not retain the merged branch tip as a parent.

That distinction is easy to miss because the readable history looks correct:

| observation | result |
|---|---|
| BASE tip | `0d386e7a5 fix(maintenance): make worktree GC answer one safety question in one place (#4708)` |
| squash commit parent | `74722a9f80988768c88dd38699e3a2cc96a74dc0` |
| PARENT tip | `efc27ee9ba68d36a46a749211517be554368f3af` |
| PARENT ancestor of BASE | no, `git merge-base --is-ancestor` exited 1 |
| PARENT ancestor of CHILD | yes, `git merge-base --is-ancestor` exited 0 |

The commit subject says PR #4708 landed. The parent graph says PARENT never
became part of BASE. Only `merge-base --is-ancestor` answers the ancestry
question.

GitHub then retargeted PR #4718. PR #4708 merged at
2026-08-07T00:15:46Z. Two seconds later, its timeline recorded
`automatic_base_change_succeeded`. PR #4718 now targets
`fix/worktree-walk-timeouts`, not the merged parent branch.

The new BASE to CHILD merge base fell back to
`b574071db8024ab51b2cffcd9818bd8d00f943d0`. That commit predates every path
reported as `add/add`:

| conflict measure | value |
|---|---|
| merge base | `b574071db8024ab51b2cffcd9818bd8d00f943d0` |
| total conflicted paths | 17 |
| `add/add` conflicts | 11 |
| content conflicts | 6 |
| `add/add` paths absent at the merge base | 11 of 11 |
| content-conflict paths present at the merge base | 6 of 6 |

An `add/add` conflict on a path inherited through a stack is the tell. Git is
not comparing the two branches from their real shared parent. Its selected
merge base predates the path.

The content comparison decides whether a bulk resolution is safe:

| measure | value |
|---|---|
| PARENT to squash changed paths | 1 |
| changed path | `tests/ci/test_walkers_skip_worktrees.py` |
| changed path overlaps the 17 conflicts | no |
| conflicted paths where BASE differs from PARENT | 0 of 17 |
| conflicted paths where CHILD differs from PARENT | 17 of 17 |

Commit `74722a9f8` changed
`tests/ci/test_walkers_skip_worktrees.py` on BASE after PARENT diverged.
Every conflicted BASE blob still equals PARENT. CHILD descends from PARENT and
changes all 17 conflicted paths. Keeping CHILD therefore loses no BASE change
on those paths. The correct tree is CHILD plus BASE's version of the one
independently changed path.

## Prevention

Before resolving a stacked conflict after a squash, compare ancestry and
content. Save the pre-squash parent tip because GitHub may delete its branch.

```bash
base=origin/fix/worktree-walk-timeouts
child=origin/fix/gc-worktrees-stale-entries
parent_tip=efc27ee9ba68d36a46a749211517be554368f3af
squash=0d386e7a564d1150344644452424e255cda24cd5

if git merge-base --is-ancestor "$parent_tip" "$base"; then
  echo "ancestry intact"
else
  echo "ancestry severed"
fi

git merge-base "$base" "$child"
git diff --name-status "$parent_tip" "$squash"
git merge-tree --write-tree --name-only "$child" "$base"
```

An empty parent-to-squash diff means the squash copied PARENT's tree exactly.
Use CHILD for every inherited path.

A short diff means the same rule applies outside the listed paths. Compare
those paths with the conflict list. Restore BASE's version for each independent
BASE change.

A large diff means the squash changed the tree during merge. Judge each path
instead of applying one bulk choice.

## Repair

This incident needs one merge and one explicit path restore:

```bash
base=origin/fix/worktree-walk-timeouts

git merge -s ours --no-commit "$base"
git checkout "$base" -- tests/ci/test_walkers_skip_worktrees.py
git commit
```

The `ours` strategy keeps CHILD's complete tree and records BASE as the second
parent. The checkout then restores BASE's sole independent change. The commit
repairs ancestry without rewriting the published CHILD branch.

Rebase is not a compliant alternative. It rewrites CHILD, so publishing it
needs a force push. `.claude/rules/universal.md` MUST NOT item 1 forbids
force-pushing a shared branch.

## Prove the repair before committing

`git write-tree` writes the index to a tree object without moving any ref or
touching the working tree, so the result can be measured before the merge is
committed:

```bash
tree=$(git write-tree)
git diff --name-only "$base" "$tree" | sort > merged.txt
git diff --name-only "$parent_tip" "$child" | sort > expected.txt
comm -23 merged.txt expected.txt   # BASE content this merge dropped
comm -13 merged.txt expected.txt   # CHILD content this merge lost
```

Both differences empty is necessary and not sufficient. An adversarial review
of this repair (grok-4.5, 2026-08-06) built the counterexample: substitute a
third blob on any one of those paths and the path still differs from BASE, so
it stays in the name list, both `comm` results stay empty, and the content is
wrong. Name-set equality proves which paths differ, never what they contain.

Add one content check, either of these:

```bash
# blob equality on every path the child owns
git diff --name-only "$parent_tip" "$child" | while read -r f; do
  [ "$(git rev-parse "$tree:$f")" = "$(git rev-parse "$child:$f")" ] || echo "MISMATCH $f"
done

# or normalized patch equality, index lines stripped
diff <(git diff "$parent_tip" "$child" | grep -v '^index ') \
     <(git diff "$base" "$tree"        | grep -v '^index ')
```

Measured on this repair: 0 blob mismatches across 31 paths, patches byte
identical, and the full 8397-path tree listing equals CHILD plus BASE's one
restored file exactly.

## Two side effects to expect

**The push ceiling can trip.** `_unpushed_commit_count`
(`scripts/validation/git_hook_policy.py`) excludes commits that some other
remote branch already carries. GitHub deletes the squashed branch on merge, so
the ~20 commits CHILD inherited from PARENT stop being excluded by any remote
ref and begin counting against CHILD. Measured here: raw 43, stack-aware 21,
limit 20, genuinely new 3. Splitting is not the remedy for an overage that the
repair merge itself caused; the `commit-limit-bypass` label is, with the
measurement recorded on the PR.

**The Commits tab looks heavier than the diff.** After the repair,
`git rev-list --first-parent "$base".."$merge"` counts 35 here while the three
dot diff is exactly CHILD's 31 files. The 14 extra are PARENT-line commits
whose trees are already in BASE through the squash. Confirmed display only:
the intersection of the PARENT-to-BASE and BASE-to-merge path lists is empty,
so no content is applied twice.

## Do not

Do not treat a PR number in `git log` as ancestry proof. Do not resolve 17
paths one at a time before checking the merge base. Do not treat a one-path
parent-to-squash diff as empty. Do not confuse `git merge -s ours` with
`git merge -X ours`; this repair keeps the whole CHILD tree, then restores
named BASE paths. Do not accept name-set equality as proof that a merge
resolution preserved content; it answers which paths differ, never what is in
them.

## Related

- `git-rebase-after-push-costs-two-cycles.md`. A published branch cannot use
  rebase without a non-fast-forward push.
- `../quality/verify-squash-merge-by-content-not-ancestry.md`. Verify squash
  results by content rather than commit reachability.
- `../decision-squash-only-breaks-ancestry-merge-detection.md`. A negative
  ancestry result does not mean a squash merge failed.
