# Diagnosing a blocked PR: read the ruleset, not mergeStateStatus

`mergeStateStatus: BLOCKED` names no cause and is not authoritative. Two PRs
in one session merged cleanly through the REST endpoint while reporting
BLOCKED. Treating the field as a verdict sends you looking for a gate that is
not holding anything.

## main has no classic branch protection

```
gh api repos/rjmurillo/ai-agents/branches/main/protection
# {"message":"Branch not protected","status":"404"}
```

That 404 is not "nothing is enforced". The repo uses rulesets. The
authoritative read is:

```
gh api repos/rjmurillo/ai-agents/rules/branches/main
```

Measured 2026-08-01, that returns: `deletion`, `non_fast_forward`,
`copilot_code_review`, `pull_request`, `code_quality`,
`required_status_checks`, `required_linear_history`.

## What actually gates a merge here

| Parameter | Value | Consequence |
| --- | --- | --- |
| `strict_required_status_checks_policy` | `false` (re-measured 2026-10-18; reverted 2026-08-10) | Being behind main does NOT block merge. Do not merge main into a branch solely to unblock it. |
| `required_review_thread_resolution` | `true` | Any unresolved review thread blocks. This is the dominant real cause. |
| `required_approving_review_count` | `0` | No human approval needed. |
| `required_status_checks` | 9 contexts (measured 2026-10-18) | A required context that is missing blocks. SKIPPED and NEUTRAL do not. |

Branch freshness is not a merge gate (strict is off). When a PR is behind
main, diagnose missing contexts or unresolved threads directly; do not refresh
the branch as a first step. GitHub never reports `BEHIND` while strict is off.
A behind branch shows `CLEAN`, `UNSTABLE`, or `BLOCKED`. The UI's "out-of-date"
banner and "Update branch" button are a suggestion, not a gate. PR #6687 on
2026-10-18 was 3 commits behind with all 9 required checks green; one
unresolved thread was the only blocker.

## The diagnosis that works

Cross-tab the ruleset's required contexts against the contexts GitHub recorded
on the PR head, and count unresolved threads. Three outcomes, three fixes:

1. Unresolved threads greater than zero. Answer the threads.
2. A required context missing or FAILURE. Read that check's log.
3. Nothing missing, nothing failing, zero threads. Nothing is holding it.
   Call the merge endpoint. It is the authority:

   ```
   SHA=$(gh pr view N --repo rjmurillo/ai-agents --json headRefOid -q .headRefOid)
   gh api -X PUT repos/rjmurillo/ai-agents/pulls/N/merge -f merge_method=squash -f sha="$SHA"
   ```

Verified on #4387 and #4328: both reported BLOCKED with all three conditions
clear, and both merged on the first call.

When rolling `statusCheckRollup` into a name-to-conclusion map, never let a
later row overwrite a SUCCESS. One workflow emits one row per trigger, so a
context can appear twice with different conclusions. Collapsing naively kept
the SKIPPED row and hid the SUCCESS, which produced a false report of a failing
required check earlier in the same session.

## Right after a push, do not wait on get_pr_checks.py

Source: the 2026-10-12 sweep (about 20 merge phases lost 10 to 35 minutes each).
The code facts were re-read on `origin/main` at `ec3214659`. The timings are
sweep observations, not re-measured.

- `get_pr_checks.py --wait` stops polling once nothing is pending
  (`PendingCount == 0`). Right after a push the required contexts have not
  registered yet. The script returns as soon as the checks already registered
  finish, even if a required context has not appeared yet, with
  `MissingRequiredChecks` set, status `FAIL`, exit 1
  (`get_pr_checks.py` lines 734 to 739 and 789 to 790). That reads as a red PR
  and is only a late start.
- The FAIL summary appends `_MISSING_RECOVERY_HINT`, which says to close and
  reopen the PR. Ignore it until `why_pr_blocked.py` confirms a context truly
  never reported. Following it in this window restarts every check for nothing.
- Poll `why_pr_blocked.py` instead, at 60 seconds or slower. It cross-tabs the
  ruleset contexts against what GitHub recorded.
- `Run Python Tests` is the `test-result` aggregator job in `pytest.yml`. It
  reports after its partitions and coverage job finish. The sweep saw it appear
  10 to 35 minutes after the splits. A missing `Run Python Tests` in that window is normal.
- `Run Python Tests` can also have a second run from the `push` event on the
  same SHA. If that run is the red one, rerun it, not only the `pull_request`
  run. See `ci/ci-job-names-collide-so-a-red-check-name-is-ambiguous`.
- `merge_pr.py` rejects while `mergeable` or `mergeStateStatus` is `UNKNOWN`
  (`_reject_unknown_merge_state`, issue #2637). The sweep saw that last about 20
  seconds after checks settled. Retry once before treating it as a block.

## The commit ceiling: superseded, no longer a merge gate (ADR-099, 2026-08-21)

**Superseded.** The block and error message quoted below no longer exist.
ADR-099 (issue #5233) removed the commit-count block and the
`commit-limit-bypass` label mechanism entirely, from both `pr-validation.yml`
and the local pre-push hook: the local check's only way to verify its own
escape hatch was a `gh api` call that a Claude Code cloud/remote session
structurally cannot make ("GitHub access is not enabled for this session"),
which forced authors into an expensive stacked-branch-and-PR workaround even
when the label was already correctly applied. `pr_commit_count.py` still
classifies a PR's commit count into `OK`/`WARNING`(>=10)/`ALERT`(>=15) and
`needs-split` still auto-applies at those thresholds, but neither status
blocks a push or a merge anymore. If you hit a commit-count-shaped BLOCKED
verdict on a PR after 2026-08-21, it is not this gate; keep reading the
ruleset per the section above.

The rest of this section is kept for historical diagnosis of PRs opened
before the removal, or for anyone reading a stale CI log that still shows it.

`Validate PR` used to be able to fail with `OVERALL_STATUS: PASS` and
`COMMIT_STATUS: BLOCKED`:

```
##[error]PR has 21 commits (limit: 20). Add 'commit-limit-bypass' label to override or split this PR.
```

The label was `commit-limit-bypass`, distinct from
`description-validation-bypass`. Applying the label did not re-evaluate on its
own; a re-run of the failed workflow was required afterward.

Finding that run needs the workflow name, not the check name. The check is
`Validate PR`; the workflow is `PR Validation`. `gh run list --workflow
"Validate PR"` returns `could not find any workflows named Validate PR`. Find
it by branch instead:

```
gh run list --repo rjmurillo/ai-agents --branch "$B" --limit 25 \
  --json databaseId,conclusion,workflowName \
  -q '.[] | select(.conclusion=="failure") | "\(.databaseId) \(.workflowName)"'
```

## Related

- `validation/validation-pr-gates.md` covers workflow authoring patterns, not
  this merge-time question.

## Count unresolved threads before labeling a PR blocked:human

Statement: before an agent labels a PR `blocked:human`, it reads the unresolved review thread count and the required check state from the PR. It names the exact blocker in the label comment. A non-required advisory check is not a blocker.

Evidence: OBSERVED 2026-10-24 on PR #6896. The agent labeled it `blocked:human` and blamed a non-required advisory check. The real block was one unresolved review thread. `get_pr_context.py` reports `review_thread_unresolved_count`, and `get_pr_checks.py` reports required check state.

