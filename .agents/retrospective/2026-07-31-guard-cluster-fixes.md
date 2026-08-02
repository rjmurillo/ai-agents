# Retrospective: Guard Cluster Fixes (Issues #3823, #3892, #3893, #3927, #3937, #3962, #3968, #3969, #3973, #3982)

## Session Info
- **Date**: 2026-07-31
- **Task Type**: Bug Fix / Analyzer Improvement
- **Outcome**: Success
- **Scope**: PR #4004 -- subprocess encoding guard and flush guard

## Learnings Captured

### What Went Well

1. **Re-measurement discipline** overturned three issues (#3823, #3927, #3968) as already fixed by
   prior PRs. Closing with evidence saves review cycles.

2. **Differential gate** (#3973) proven before other changes. Running `guard_diff.py` against the
   corpus baseline caught one early false-positive from the R3 fix before it was committed.

3. **Mutation harness** caught two weak tests: the non-constant-key `_has_splat` test initially
   had no negative case; the depth-bound test did not verify the returned finding message.

4. **Policy decisions** for #3962 and #3893 were written down and pinned with tests. Explicit wontfix
   is better than silent behavior.

### What Went Wrong

1. **Type-ignore ratchet divergence**: The pre-push hook runs against the CI merge commit, not just
   our branch. When main added a `type: ignore` without bumping the baseline, our rebase picked up
   the baseline bump but not the suppress removal. Fix: always remove the suppress AND verify the
   count in the merge commit scenario, not just locally.

2. **Stale `.pyc` hazard in mutation harness**: Same-length edits restored within one second reuse
   stale bytecode. Future harness runs must either change file mtime or sleep 1s between mutant and
   restore.

3. **Stale untracked file from `git stash pop`**: Left
   `src/copilot-cli/hooks/preToolUse/invoke_skill_first_guard__Bash_f620ca.py` on disk, causing a
   test that rglobs the directory to fail. Running `git status --short` after every stash operation
   is now a hard rule.

4. **Corpus baseline line-number drift**: After main merged PRs that shifted lines in
   `.claude/skills/` files, the baseline was stale. The differential gate test caught this
   immediately. Baseline refresh is now part of the rebase checklist.

### Process Improvements

- `git status --short` after every `git stash pop` before running any test.
- Mutation harness must add 1s sleep or force-touch between mutant and restore.
- Corpus baseline refresh belongs in the post-rebase checklist, not as an afterthought.
- The retrospective-policy gate requires a retrospective file dated today or yesterday. Add
  creating the retro file as the first step of any multi-day campaign, not the last.
