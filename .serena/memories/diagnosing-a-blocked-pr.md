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
| `strict_required_status_checks_policy` | `true` | Being behind main DOES block. Merge `origin/main` into the branch to unblock it. Changed since 2026-08-01; this row read `false` until 2026-08-05. |
| `required_review_thread_resolution` | `true` | Any unresolved review thread blocks. This is the dominant real cause. |
| `required_approving_review_count` | `0` | No human approval needed. |
| `required_status_checks` | 17 contexts | A required context that is missing blocks. SKIPPED and NEUTRAL do not. |

Every open PR in the repo is behind main at any given moment, so under the old
`strict: false` setting "behind main" could never discriminate between a blocked
PR and a mergeable one. It was a detector that cannot fail, which means it had
not been run.

That reasoning expired on 2026-08-05, when the ruleset began enforcing
`strict_required_status_checks_policy: true`. "Behind main" now discriminates
precisely, because it is a merge blocker rather than ambient noise. Measured the
same day across all open PRs: 41 BEHIND, 13 DIRTY, 1 BLOCKED, 0 CLEAN. Being
behind is now the dominant blocking condition, not an unusable signal.

There is still no merge queue, so nothing makes a branch current on its own.
Each BEHIND PR needs an explicit update, and every merge returns the rest to
BEHIND. Prefer the server-side update, which needs no local checkout and cannot
collide with an in-flight push:

```
gh api -X PUT repos/rjmurillo/ai-agents/pulls/<n>/update-branch \
  -f expected_head_sha=<full 40-char head sha>
```

A truncated SHA returns HTTP 422. The full 40 characters are required.

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

## The commit ceiling is a separate gate with its own escape hatch

`Validate PR` can fail with `OVERALL_STATUS: PASS` and `COMMIT_STATUS: BLOCKED`:

```
##[error]PR has 21 commits (limit: 20). Add 'commit-limit-bypass' label to override or split this PR.
```

The label is `commit-limit-bypass`, distinct from
`description-validation-bypass`. Applying the label does not re-evaluate on its
own; re-run the failed workflow afterward.

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
