# /autofix-pr

Autonomous PR monitor and fixer. Implements the protocol from
`docs/autonomous-pr-monitor.md`.

## Workflow

1. Triage all open PRs into tiers T1-T5 using `test_pr_merge_ready.py`.
2. Process T1 (land-ready) first, then T2 (CI fix), T3/T4 (threads), T5 (bot).
3. For each PR: address review threads, fix CI failures using known patterns, enable auto-merge.

## Ready-to-Merge Definition (4 conditions, ALL required)

1. Branch up to date with `main` (`mergeStateStatus` not `BEHIND`).
2. All required checks pass.
3. All conversations addressed: READ, TRIAGED, SOLVED (if Blocking), REPLIED with course of action, RESOLVED.
4. `mergeStateStatus == CLEAN` (or `UNSTABLE` with documented non-required failures).

`CanMerge=True` from `test_pr_merge_ready.py` alone is insufficient. Cross-check all four conditions.

## Tier Definitions

| Tier | Criteria | Action |
|------|----------|--------|
| T1 | Branch up to date, no CI failures, no threads, `CLEAN` | Enable auto-merge |
| T2 | CI failures only, branch up to date | Fix CI, verify required checks pass |
| T3 | Threads only (CI passing) | Walk full thread lifecycle, then merge |
| T4 | Both CI failures + threads | Fix CI first, then lifecycle threads |
| T5 | Bot PR with validation failures | Handle individually |

If `BEHIND`, update branch against main BEFORE other actions (see doc Branch Update section).

## Fix Patterns

- **PR description mismatch**: Remove file references not in the diff (use GitHub API to PATCH body).
- **Branch behind main**: Worktree + `git merge origin/main --no-edit` + push (no force needed).
- **Stale CI check**: Push fresh commit to re-trigger; avoid `--no-verify` if possible.
- **Bot review threads**: Read, triage per Thread Severity, reply with disposition, resolve via `add_pr_review_thread_reply.py --resolve`.
- **Session validation failure**: Use session-log-fixer skill.

## Force-Push Safety

Before any push: verify `cat .git/refs/heads/<branch>` matches expected SHA. If local ref points to a bootstrap/sandbox commit, STOP. Investigate corruption before pushing. Force-push only with explicit user authorization, using SHA-pinned source: `git push origin <SHA>:refs/heads/<branch> --force-with-lease`.

## Scripts

```bash
# Check merge readiness
python3 .claude/skills/github/scripts/pr/test_pr_merge_ready.py --pull-request {pr}

# Get CI check logs
python3 .claude/skills/github/scripts/pr/get_pr_checks.py --pull-request {pr} | \
  python3 .claude/skills/github/scripts/pr/get_pr_check_logs.py --pull-request {pr} --checks-input -

# Enable auto-merge
python3 .claude/skills/github/scripts/pr/set_pr_auto_merge.py --pull-request {pr} --enable --merge-method SQUASH
```

## Completion Gate

Run after all threads resolved and CI passes:

```bash
python3 .claude/skills/github/scripts/pr/run_completion_gate.py \
  --config .claude/commands/pr-review-config.yaml \
  --pull-request {pr} --json
```
