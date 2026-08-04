# Retrospective Section: Validate PR Fleet Repair

**Date**: 2026-08-04
**Scope**: Repair failing Validate PR gates for PRs 4078, 4216, 4392, and 4433
**Branches**: fix/github-skill-cluster, fix/stale-manifest-bump-guidance, fix/4305-followup-review-repairs, test/command-aware-subprocess-fake

## Learnings Captured

### Check-run API beats PR rollup for this gate

`gh pr view` mixed rows across triggers and re-runs. The commit check-runs API gave the real failing run per head SHA. That avoided fixing stale failures.

### PR body validation treats inline paths as changed-file claims

PRs 4078 and 4216 failed because the body cited paths outside the changed-file sections. Rewriting tool citations as prose kept the validation claim focused on the actual diff.

### Stale branches can hide as Validate PR failures

PRs 4392 and 4433 refuted the backtick-path hypothesis. Their first blocker was the taste count ratchet after main moved. Syncing main was required before the gate could give useful signal.

### Local pre-push gates need live credentials and exact baselines

The Copilot plugin smoke uses the active token. Exporting `GH_TOKEN`, `GITHUB_TOKEN`, and `COPILOT_GITHUB_TOKEN` from `gh auth token` avoids stale environment credentials. The shipped taste baseline must match the tracked tree exactly, not only pass the ratchet slack check.
