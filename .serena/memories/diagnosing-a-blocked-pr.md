# Diagnosing a blocked PR: read the ruleset, not mergeStateStatus

`mergeStateStatus: BLOCKED` names no cause and is not authoritative. Two PRs
in one session merged cleanly through the REST endpoint while reporting
BLOCKED. Treating the field as a verdict sends you looking for a gate that is
not holding anything.

## `UNKNOWN` in a bulk PR query is not an answer

A repo-wide GraphQL query for `mergeStateStatus` across every open PR can come
back almost entirely `UNKNOWN`. Measured 2026-08-05: 53 of 55 open PRs returned
`UNKNOWN` in one call, minutes after a per-PR REST read had returned a definite
`blocked` for one of them.

The tempting inference is that bulk queries serve stale or lazily-computed data
and that only per-PR access forces GitHub to compute the real value. That is
wrong. Tested by issuing the bulk query and two per-PR queries inside a single
command, so no time passed between them: bulk and per-PR agreed exactly, both
`BEHIND` for both PRs. Re-running the bulk query a few minutes later returned a
fully resolved distribution with no `UNKNOWN` at all.

GitHub documents `UNKNOWN` as "not computed yet." In this observation it later
resolved without per-PR fallback calls. Treat it as incomplete data. Wait and
re-query rather than inventing a cause.

This matters because acting on the wrong inference is expensive. Falling back to
one REST call per PR turns a single query into 55 and burns a separate API
budget. Wait and re-query instead.

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
| `strict_required_status_checks_policy` | `true` | Being behind main blocks. Updating the branch clears this freshness blocker, but other gates may remain. Measured `false` on 2026-08-03 and `true` on 2026-08-05; the flip is not timestamped by any API, so do not infer a date. |
| `required_review_thread_resolution` | `true` | Any unresolved review thread blocks. |
| `required_approving_review_count` | `0` | No human approval needed. |
| `required_status_checks` | 17 contexts | A required context that is missing blocks. SKIPPED and NEUTRAL do not. |

Under the old `strict: false` setting, being behind was not itself a merge gate
and therefore could not explain `BLOCKED`.

That reasoning has expired. The ruleset now enforces
`strict_required_status_checks_policy: true`. A `BEHIND` result now proves a
freshness blocker. Measured across the 56 open PRs on 2026-08-05: 41 BEHIND,
13 DIRTY, 1 BLOCKED, 0 CLEAN. Those sum to 55, so one PR held a state I did not
record.

There is still no merge queue. In the measured queue, no automatic updater kept
branches current. Prefer the server-side update, which needs no local checkout:

```
gh api -X PUT repos/rjmurillo/ai-agents/pulls/<n>/update-branch \
  -f expected_head_sha=<full 40-char head sha>
```

`expected_head_sha` is optional. When supplied, it must exactly match the full
head SHA. A truncated SHA mismatches and returns HTTP 422.

This is optimistic concurrency, not collision prevention. If a local push wins
first, the update rejects the stale expected SHA. If the update wins first, the
local push rejects as non-fast-forward.

The update creates a merge commit on the remote branch, so any local clone or
worktree tracking that branch is immediately one commit stale. A local push
after this is rejected as non-fast-forward. That rejection is the expected
result of your own update, not a sign that a sibling agent pushed. Pull before
committing anything further to that branch.

After an update, required contexts must report on the new head before it can
merge. Do not promise a transient `mergeStateStatus` value.

## The diagnosis that works

Check freshness first. Then cross-tab the ruleset's required contexts against
the contexts GitHub recorded on the PR head, and count unresolved threads.
Four outcomes, four fixes:

1. `mergeStateStatus: BEHIND`. Update the branch. This value proves a freshness
   blocker under the current strict policy.
2. Unresolved threads greater than zero. Answer the threads.
3. A required context missing or FAILURE. Read that check's log.
4. The branch contains current `main`, nothing is missing or failing, and
   unresolved threads are zero. Call the merge endpoint. It is the authority:

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
