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
set -euo pipefail
export LC_ALL=C

tree=$(git write-tree)
git diff --name-only "$base" "$tree" -- | sort > merged.txt
git diff --name-only "$parent_tip" "$child" -- | sort > expected.txt
comm -23 merged.txt expected.txt   # BASE content this merge dropped
comm -13 merged.txt expected.txt   # CHILD content this merge lost
```

`set -euo pipefail` and explicit refs are load bearing, not decoration. With an
unset or misspelled ref both `git diff` calls exit fatally, `sort` still exits 0
and writes an empty file, and both `comm` results come back empty. The check
then certifies a tree nobody compared. An empty `comm` is only evidence when
you can show both inputs were non-empty.

Both differences empty is necessary and not sufficient. An adversarial review
of this repair (grok-4.5, 2026-08-06) built the counterexample: substitute a
third blob on any one of those paths and the path still differs from BASE, so
it stays in the name list, both `comm` results stay empty, and the content is
wrong. Name-set equality proves which paths differ, never what they contain.

Add a content check that compares whole tree entries, with rename detection off:

```bash
set -euo pipefail
git diff --name-only --no-renames -z "$parent_tip" "$child" -- |
while IFS= read -r -d '' f; do
  [ "$(git ls-tree "$tree" -- "$f")" = "$(git ls-tree "$child" -- "$f")" ] \
    || { echo "MISMATCH $f"; exit 1; }
done
```

Three details each close a hole a second review (gpt-5.6-sol, 2026-08-06)
demonstrated:

- **`--no-renames`.** With rename detection on, a rename shows only the new
  path, so a tree that wrongly kept the old path too passes. Disabling it lists
  both sides, and the old path then mismatches.
- **`git ls-tree` rather than `git rev-parse "$tree:$f"`.** `ls-tree` compares
  mode, type, and object id, so a `100644` to `100755` flip is caught. It also
  prints nothing for an absent path instead of failing, which makes present
  against absent a visible mismatch rather than an error.
- **`-z` with `read -d ''`.** A path containing a newline or a quote otherwise
  splits or arrives escaped.

Normalized patch equality (`git diff ... | grep -v '^index '` on both sides) is
a weaker second opinion, not a substitute: two distinct binary blobs produce
identical patch text once the index lines are stripped.

Measured on this repair: 0 mismatches across 31 paths, and the full 8397-path
tree listing equals CHILD plus BASE's one restored file exactly. This incident
had 23 modifications, 8 additions, no deletions, no renames, and no binary
files, so the weaker checks happened to agree here. That is luck, not evidence.

## Two side effects to expect

**The push ceiling used to be able to trip; it cannot anymore (ADR-099,
2026-08-21, issue #5233).** `_unpushed_commit_count`
(`scripts/validation/git_hook_policy.py`) still counts with
`git rev-list --count <sha> --not --exclude=origin/<branch> --remotes=origin`,
so it still excludes commits carried by any *other* `refs/remotes/origin/*`
ref (that part of this section is unchanged and still useful for
understanding why the counted figure moves when a tracking ref is pruned).
What changed is the consequence: `_check_commit_limit`, the function this
count fed into, no longer blocks a push at any threshold, and the
`commit-limit-bypass` label and its human-only-maintainer step were removed
entirely, because the label could not be reliably verified from inside a
sandboxed Claude Code session. If a repair merge like this one now pushes a
count over the old 20/40 thresholds, the only visible effect is the
advisory `needs-split` label and a WARNING/ALERT notice; nothing blocks the
push. Measured here (before the removal) with the PARENT tracking ref still
present: raw 43, counted 21, limit 20, genuinely new 3; removing that
tracking ref raised the counted figure to 35. That specific measurement is
kept as a worked example of how the count moves, not as a description of a
live block.

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
