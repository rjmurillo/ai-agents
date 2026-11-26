# chestertons-fence: before and after the checker revision

Run `20261126T000000Z-cf0dogfd`, 2026-11-26. Model `claude-haiku-5-5`, 3 reps per task.
Raw records are under `../../runs/20261126T000000Z-cf0dogfd/`. Scores are in `capability.json`.

## Arms

| Arm | Checkout HEAD | Skill |
|---|---|---|
| before | `8104f11665` (the `base_commit`) | chestertons-fence 1.1.0 |
| after | `9e1840558`, a local commit on `8104f11665` | chestertons-fence 1.2.0: probe by target kind, Step 2 checker, Gotchas |

The after commit changes only the skill's `SKILL.md`. Each arm ran in a standalone
clone of `origin/main`. Neither clone holds the tasks file, and no ref in either
reaches a commit that touched it. The runner now refuses any other setup.

## Result

| Task | Trap | Before F1 | After F1 | Before turns | After turns |
|---|---|---|---|---|---|
| Q1-moved-file | B3 mirror add commit | 1.00 | 1.00 | 4.0 | 4.3 |
| Q2-section-in-file | none recorded | 1.00 | 1.00 | 5.3 | 4.7 |
| Q3-rule-line | B2 template move | 1.00 | 1.00 | 7.7 | 9.0 |
| Q4-gate-script | none recorded | 1.00 | 1.00 | 3.7 | 3.3 |

Totals over 12 runs each: 0 errors in both arms. Before used 62 turns and $0.221.
After used 64 turns and $0.248.

Status: no gap. Both arms answer every task correctly, so this set cannot show
whether the checker helps. The after arm used about 3 percent more turns and
12 percent more dollars. Q3 turns ranged 6 to 10 before and 8 to 10 after, so
three reps cannot separate that cost from noise.

## Invalid runs, not scored

Two earlier attempts ran in linked worktrees. The first put the tasks file in
both checkouts, and one before run's transcript referred to it. The second
removed the file, but a linked worktree shares its main repository's refs, so
`git log --all` could still reach the gold. Both were discarded. The runner's
gold check came out of them.

## Confound

The child CLI loads the operator's user hooks. One hook truncated a large
`SKILL.md` read in an early run. Both arms share the same hooks.

## Next measurement

A harder set would separate the arms: a weaker model, or tasks where the first
probe returns the trap commit unless the agent runs the second probe.
