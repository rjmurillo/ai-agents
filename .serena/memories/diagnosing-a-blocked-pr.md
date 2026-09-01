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
| `strict_required_status_checks_policy` | `false` (measured 2026-08-14; reverted 2026-08-10) | Being behind main does NOT block merge. Do not merge main into a branch solely to unblock it. |
| `required_review_thread_resolution` | `true` | Any unresolved review thread blocks. This is the dominant real cause. |
| `required_approving_review_count` | `0` | No human approval needed. |
| `required_status_checks` | 17 contexts | A required context that is missing blocks. SKIPPED and NEUTRAL do not. |

Branch freshness is not a merge gate (strict is off). When a PR is behind
main, diagnose missing contexts or unresolved threads directly; do not refresh
the branch as a first step.

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
