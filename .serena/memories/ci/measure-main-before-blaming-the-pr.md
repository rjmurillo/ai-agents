# Skill: Measure main before attributing a gate failure to a PR (95%)

## Statement

When several open PRs fail the same check, measure the gate against a clean
`origin/main` worktree before reading any of the failures as PR-caused. A
whole-repo ratchet compares the working tree to a committed baseline, so the
moment main crosses its own baseline every PR that merges main inherits the
failure and every per-PR investigation is wasted.

## Evidence

2026-08-02, pr-autofix over 38 open PRs. Four PRs (#4284, #4271, #4274, #4256)
each showed exactly one red check, `Run Python Tests`, failing on
`tests/ci/test_count_ratchet_against_real_git.py::test_the_shipped_baseline_matches_the_tracked_tree`.
The message named a delta and no path.

Measured on a clean detached worktree at `origin/main`:

```
baseline: 601
taste-lints: 7771 files scanned, 602 error(s), 717 warning(s)
```

Main was one over its own baseline. The PRs were green on their own content:
`taste_lints.py --diff-scope origin/main` reported `0 error(s)` for the changed
files of #4256. The cause was `pre_pr_sequence.py` crossing the 500-line
file-size ceiling on main, already fixed in flight by PR #4290.

## Recipe

```bash
git worktree add <tmp> --detach origin/main
cd <tmp> && git clean -qfd
python3 .claude/skills/taste-lints/scripts/taste_lints.py -d . --format text | tail -2
cat scripts/ci/taste_count_baseline.txt
```

Count over baseline means main is red. Stop triaging individual PRs; find or
open the PR that clears main, land it, then re-run the queue.

## Cost of skipping it

Four independent investigations, roughly 13 minutes of CI each per re-run, all
converging on a cause that lives on main. The per-PR signal cannot distinguish
inherited from introduced: both render as the same one-line assertion.

## Related

- `ci/ci-count-ratchet-never-names-the-offending-file` for locating the file
  once you know which tree is over.
- Issue #4207 (the ratchet message names no path).
