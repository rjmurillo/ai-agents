# Let pr-autofix drive a PR

## Goal

Hand a PR to `pr-autofix`. It fixes red checks and review threads, stops at a
round limit, and merges only when four conditions hold.

## Before you start

- `gh auth status` shows you are signed in. `uv` and `python3` are installed.
- You know the PR number, or you are on the PR's branch.
- Read [pr-review](how-to-pr-review.md). `pr-autofix` is for fixing a red check.
  `pr-review` is for answering comments and getting a verdict.

## Steps

1. Pick a mode by what you say:

   | You say | What happens |
   |---|---|
   | `pr-autofix` | Triage all open PRs by tier and act. |
   | `autofix this pr` | Work the current branch's open PR. |
   | `monitor open prs` | Periodic triage without merging. |
   | `auto-merge ready prs` | Tier 1 only: enable auto-merge on land-ready PRs. |
   | `address pr feedback` | Tiers 3 and 4 only: walk the thread lifecycle. |

2. Learn the tiers. The skill reads each PR's state with
   `test_pr_merge_ready.py`, which is the one source of the tier.

   | Tier | PR state | Action |
   |---|---|---|
   | T1 | Ready to merge | Merge by the path for its state. |
   | T2 | Failing checks only | Fix CI. |
   | T3 | Open threads only | Walk the thread lifecycle, then merge. |
   | T4 | Failing checks and open threads | Fix CI first, then the threads. |
   | T5 | Bot-authored PR with failures or threads | Hand to a person. |

   Merge conflicts, unknown merge states, and stacked PRs never enter the fix
   loop. The skill disarms auto-merge and hands them to a person.

3. Ask first whether a red check is yours. For a failing check, the skill runs
   `triage_red_check.py`. Red on `main` too means it is inherited. The skill
   cites the evidence and does not debug your PR. `UNKNOWN` is never read as green.

4. Understand the circuit breaker. T3 and T4 PRs loop: push a fix, wait for CI or a
   bot, repeat. Before the breaker existed, one PR ran more than 11 bot rounds over
   46 hours. Now each pass calls `check_pr_round_cap.py`. It records one round and
   answers `ACT` or `ESCALATE`.

   | Setting | Default | Override |
   |---|---|---|
   | Rounds | 5 | `--max-rounds` or `PR_AUTOFIX_MAX_ROUNDS` |
   | Wall clock | 4 hours | `--max-hours` or `PR_AUTOFIX_MAX_ROUND_HOURS` |

   On `ESCALATE` the script posts the reason as a PR comment, and the skill stops
   working that PR. The wall-clock budget restarts when the PR head moves. A
   maintainer restarts both the clock and the round count by commenting
   `/pr-autofix continue`. The commenter must be the repo owner or a collaborator.
   The same reset exists as `--reset` on the script.

5. Treat unpushed commits as unverified. After an escalation, the script lists
   commits on your local branch that never reached the PR. One such commit once
   deleted a pre-push job and the test guarding it. Read each commit's diff, run
   its tests, and push only the ones that pass.

6. Check the four Ready-to-Merge conditions. All four must hold:

   1. No merge conflict with `main`. Being behind `main` is not a conflict.
   2. All required checks pass.
   3. Every conversation is read, triaged, solved if blocking, replied to, and
      resolved.
   4. `mergeStateStatus` is `CLEAN` or `HAS_HOOKS`, or `UNSTABLE` with every
      non-required failure documented.

   `CanMerge=True` from `test_pr_merge_ready.py` is one input. It is not the gate.

   Do not update a branch just because it is behind. Each update re-runs that PR's
   CI, and each merge puts every other open PR behind again. This repo's ruleset sets
   `strict_required_status_checks_policy` to false, so a behind branch can still
   merge. See [Serial landing](../landing-workflow.md) for the cost.

7. Merge pinned to the head SHA. The skill reads the head at triage and passes it to
   the merge script. A moved head is refused:

   ```bash
   python3 .claude/skills/github/scripts/pr/merge_pr.py --pull-request <PR> \
     --strategy squash --expected-head-sha <40-hex head SHA> --dry-run
   ```

   `--dry-run` runs every pre-merge check and makes no merge call. Drop it to
   merge. GitHub checks branch protection at merge time, not in the dry run.

## When automation must not merge

- A PR that changes `.agents/governance/**` needs a human maintainer. Auto-merge
  is off for it ([landing workflow](../landing-workflow.md)).
- A PR whose base is not the default branch is stacked. A squash would collapse the
  stack onto its parent. A person lands it.
- Replying and resolving the last thread disarms auto-merge first. Check whether it
  is still armed before you wait for a merge.

For the ruleset itself, see [merge guards](../merge-guards.md). Check the live rules
before you trust a number in any doc:

```bash
gh api repos/rjmurillo/ai-agents/rules/branches/main
```

## Check your result

- The PR is merged, or `ESCALATE` posted a comment with a reason.
- Nothing merged while a required check was red or a thread was open.
- `git ls-remote origin <branch>` shows whether the branch still exists. This repo
  deletes merged branches, so an empty answer is normal.

## If it fails

| What you see | What to do |
|---|---|
| `ESCALATE` after 5 rounds or 4 hours | Read the PR comment. Fix the cause by hand, or comment `/pr-autofix continue`. |
| `UNSUPPORTED` or `STACKED` tier | A person merges it. |
| `merge_pr.py` refuses the SHA | The head moved. Re-read the PR and re-check the four conditions. |
| A required check stays red on `main` | Wait for `main` or fix `main`. Do not change your PR. |

## Next

- [Get a maintainer decision](how-to-maintainer-review.md)

## Reference

- [pr-autofix skill](../../.claude/skills/pr-autofix/SKILL.md)
- [Serial landing workflow](../landing-workflow.md)
- [Merge guards](../merge-guards.md)
- [ADR-112: risk-tiered action boundaries](../../.project-toolkit/architecture/ADR-112-risk-tiered-action-boundaries.md)
