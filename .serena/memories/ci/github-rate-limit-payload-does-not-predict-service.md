# `gh api rate_limit` Does Not Predict Whether a Call Will Be Served

`gh` refuses requests with "API rate limit exceeded" while `rate_limit` reports
the matching bucket as nearly full. So the obvious diagnostic step, read the
error and then check the quota, produces a contradiction rather than an answer.
Do not conclude from a healthy `rate_limit` payload that the API is available.

## The measurement

Taken in one fleet session with roughly ten concurrent agents, all within one
minute of each other:

```
$ gh pr view 4303 --repo rjmurillo/ai-agents --json state
GraphQL: API rate limit already exceeded for user ID 6811113.

$ gh run list --repo rjmurillo/ai-agents --branch main --limit 3
failed to get runs: HTTP 403: API rate limit exceeded for user ID 6811113
    (https://api.github.com/repos/rjmurillo/ai-agents/actions/runs?...)

$ gh api repos/rjmurillo/ai-agents --jq .full_name
{"message": "API rate limit exceeded for user ID 6811113", ...}

$ gh api rate_limit --jq '.resources | "core=\(.core.remaining) graphql=\(.graphql.remaining)"'
core=4948 graphql=0
```

Both REST calls hit `core`, which reports 4948 of 5000 remaining, and both are
refused. `gh api rate_limit` answers throughout because it is exempt from rate
limiting.

Earlier in the same session, the same shape appeared with `graphql` also healthy:

```
20:09  gh api repos/.../rules/branches/main   403      core=2860  graphql=3908
20:15  gh run list                            403      core=4984  graphql=1694
```

Each of those cleared on its own, and the next call of the same shape succeeded
about a minute later, well before either `reset` timestamp.

## What is established and what is not

Established by the measurements above:

- A 403 "rate limit exceeded" on a REST endpoint does not imply the `core`
  bucket is drained. It was 99 percent full during a refusal.
- The refusals recover in about a minute, far sooner than `reset` suggests.
- `gh pr view` fails with a distinct GraphQL-named message and tracks the
  `graphql` bucket. `gh run list` and `gh api <path>` fail with an HTTP 403 and
  a REST URL.
- `gh api rate_limit` keeps answering when everything else is refused.

Not established. The mechanism. A secondary or abuse limit keyed on request
velocity fits, and so does an account-wide throttle triggered by draining the
GraphQL bucket, since both REST and GraphQL were refused together in the last
observation. These were not separated, so do not repeat either as the cause.

## What to do

Treat any "rate limit exceeded" as a 60 second backoff first. Retry once before
investigating. Only if it persists past a couple of minutes is it worth reading
`reset` and planning around a real quota exhaustion.

Do not spend time reconciling the error against `rate_limit`. The numbers will
look fine and the reconciliation has no payoff.

## Repo tooling does not handle this

`scripts/github_core/api.py:261` treats only 429 and 5xx as transient, so a 403
raises immediately rather than retrying, even though these refusals clear in
about a minute. `scripts/github_core/rate_limit.py:93`
`check_workflow_rate_limit` reads only the `rate_limit` payload, so it returns
`success=True` during a refusal window and its three production callers proceed
into work that will fail call by call. Filed together; search issues for
"403 rate-limit refusal is never retried".

## Under fleet operation

This fired every few minutes with about ten concurrent agents. Prefer one wide
query over several narrow ones, avoid parallel API reads across agents, and
budget for the backoff rather than treating each refusal as a new problem.
