# Skill: The live-state gate expires while you do the work (HIGH, correction)

## Statement

`check_pr_live_state.py` answers "is this PR actionable **right now**". The
pr-autofix protocol says to call it immediately before each per-tier action, and
"immediately" is the load-bearing word. A verdict collected during triage is
stale by the time thread work, a test run, and a merge have finished.

Re-run the gate in the same command as the push, not at the top of the batch.

## Evidence

2026-08-02, session 4234. Gated eight PRs in one loop at the start of the walk;
all returned `ACT`. Then spent roughly forty minutes on #4282: regenerating an
episode, restoring `metrics.files_changed`, running the corpus validator. The
push reported:

```
 * [new branch]          HEAD -> fix/episode-store-backwards-chains
```

`[new branch]` on a branch that already had an open PR is the tell. #4282 had
merged mid-walk and GitHub had deleted the head ref; the push recreated it,
carrying a commit no PR pointed at. `gh pr view 4282` then read
`MERGED  fix/episode-store-backwards-chains  55ac2082d`.

Recovery: `git push origin --delete <branch>`, keep the commit on a local
`keep/` branch, open a fresh issue and PR against main. Cost was one wrong push
plus the branch and PR that should have been opened in the first place.

Two of eight (#4271, #4274) merged during the same walk. On a repo with merge
automation, a triage snapshot over eight PRs decays inside one working session.

## Recipe

Fold the gate into the push step so no work can happen between them:

```bash
ACTION=$(python3 "$SCRIPTS_DIR/check_pr_live_state.py" --pull-request "$PR" \
    --skip-fetch --output-format json | jq -r '.Data.action')
[ "$ACTION" = "ACT" ] || { echo "skip $PR"; exit 0; }
git push origin "HEAD:refs/heads/$BRANCH"
```

Cheap independent tell that needs no extra call: a push to an existing PR branch
prints a range (`abc123..def456`). `* [new branch]` means the ref was gone, so
stop and check the PR state before doing anything else.

## Related

- `ci/ci-mergeability-is-not-computed-until-you-ask`
- Issue #2455, which introduced the per-PR gate for this exact failure.
