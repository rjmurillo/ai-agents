# `git diff origin/main` shows main's additions as your branch's deletions

## Symptom

You read `git diff origin/main -- <file>` on a feature branch, see a block of
`-` lines removing something useful, and conclude your PR deletes it. You then
"restore" code your branch never touched, or you file a review finding against
a change nobody made.

## Cause

`git diff <ref>` compares `<ref>` to your working tree. Every line present in
`<ref>` and absent from your tree renders as a deletion, whether your branch
removed it or your branch simply predates it. On a branch cut before a commit
landed on main, main's additions and your deletions are spelled identically.

Observed 2026-08-02 on `fix/gc-report-time-budget`. `git diff origin/main --
tests/test_validation_command_size.py` showed an `_isolate_ci_env` autouse
fixture and a test being removed. The branch had removed neither. PR #4368 had
added both to main after the branch was cut. The same reading on
`fix/portability-baseline-at-ref` produced the same false conclusion.

## The discriminating check

Ask whether the symbol exists on each branch independently, rather than reading
a two-way diff:

```bash
for ref in origin/main origin/<your-branch>; do
  printf "%-40s " "$ref"
  git show "$ref:<path>" 2>/dev/null | grep -q "<symbol>" && echo HAS || echo MISSING
done
```

`MISSING` on your branch and `HAS` on main means you are behind, not
destructive. Confirm with `git log --oneline -3 origin/main -- <path>`, which
names the commit that added it.

The fix for "behind" is `git merge origin/main` (or a rebase). The fix for a
real deletion is a restore. They are opposite actions, so the check is worth
the two seconds.

## Related

- `new-pr-stale-main-ref-trap.md` covers the neighbouring failure where a
  script diffs the stale **local** `main` ref instead of `origin/main`. Same
  family, different mechanism: that one is a wrong base, this one is a correct
  base read in the wrong direction.
