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

Narrowed later in the same session. Two candidate mechanisms fit the readings
above: a secondary limit keyed on request velocity, or an account wide throttle
triggered by draining the GraphQL bucket, since REST and GraphQL were refused
together at 20:25 with `graphql=0`. A later measurement separates them:

```
20:25  gh run list             403   core=4948  graphql=0
20:25  gh api repos/...        403   core=4948  graphql=0
20:50  gh pr list              refused (GraphQL)
20:50  POST /repos/.../issues  201   core=3079  graphql=0
```

GraphQL stayed exhausted across both readings while REST went from refused to
serving. An exhausted GraphQL bucket is therefore not sufficient to refuse REST,
and the account wide throttle explanation does not survive that. The velocity
explanation is the better supported of the two. It is not proven, so still
describe a refusal as a refusal rather than naming a cause.

The operational consequence is concrete. When GraphQL is exhausted, REST is
often still serving, so prefer the REST shape of an operation when one exists.
`gh issue create` and `gh pr create` go through GraphQL, but
`POST /repos/{owner}/{repo}/issues` and `POST /repos/{owner}/{repo}/pulls` do
not, and both worked in this window.

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
into work that will fail call by call. Both are issue #4326.

`.claude/skills/github/scripts/issue/new_issue.py` speaks GraphQL, so it cannot
file an issue while GraphQL is exhausted even though the REST issue endpoint is
serving. Confirmed by failing that script and then filing the same issue through
`POST /repos/rjmurillo/ai-agents/issues` in the same minute. When a github skill
script fails with a GraphQL rate limit, the REST equivalent is worth one try
before waiting.

## Under fleet operation

This fired every few minutes with about ten concurrent agents. Prefer one wide
query over several narrow ones, avoid parallel API reads across agents, and
budget for the backoff rather than treating each refusal as a new problem.

## It takes the AI quality gate down, and the PR does not say so

A refusal during the AI review workflow does not surface as a rate limit
anywhere a reader looks first. The chain, observed on PR #4471 at
`2026-08-03T18:15:49Z`:

1. The context build step shells out to `gh` to fetch PR data and takes a 403.
   The log line is a `##[warning]`, not an error: `PR fetch failed: gh: API
   rate limit exceeded for user ID 6811113`.
2. `scripts/ci/check_ai_review_infra_gate.py` sets `CONTEXT_INFRA_FAILURE:
   true` and every agent skips its Copilot CLI invocation.
3. All ten agents report `DID_NOT_RUN (infra: true)`: security, qa, analyst,
   architect, devops, roadmap, reliability, observability, agent-safety,
   decision-rigor.
4. `Aggregate Results` exits 1. That single red check is the only thing visible
   on the PR, and its own log says nothing about rate limits.

`gh pr checks` makes it worse: the individual agent jobs report **pass**,
because skipping cleanly is a successful job. Only `Aggregate Results` is red.
The natural reading, that the aggregation logic is broken or the diff failed
review, is wrong both times.

Diagnose it by opening any one agent job's log and grepping for `INFRA` or
`rate limit`, not by reading the aggregate job. A uniform `DID_NOT_RUN` across
all ten agents is the tell: a real review failure never hits every agent at
once.

The fix is a **full** re-run, `gh run rerun <run-id>`, once the bucket resets.
`gh run rerun <run-id> --failed` does not work and the reason is the same
asymmetry: the agent jobs are green, so `--failed` re-runs only `Aggregate
Results`, which re-downloads the identical stale `DID_NOT_RUN` artifacts and
fails identically. Measured on PR #4471: the `--failed` rerun aggregated at
`18:44:56` against agent verdicts still stamped `18:15:49`, with core quota
recovered to 4894/5000 at the time. Quota headroom is not the variable; which
jobs re-run is.

Nothing in the diff needs to change. Check `gh api rate_limit` for the reset
timestamp first, keeping in mind that a healthy payload does not prove the API
is serving, per the measurement above.
## There are two refusal modes, and the failing response tells you which

The guidance above ("the numbers will look fine", "treat it as a 60 second
backoff") holds for one of two modes. A later measurement found the other, and
the two want opposite responses. The discriminator is the response header on the
refused call itself, which neither `gh api rate_limit` nor the error body
carries.

Read it with `-i`:

```
$ gh api user -i
Date: Mon, 03 Aug 2026 18:30:15 GMT
X-Ratelimit-Remaining: 0
X-Ratelimit-Reset: 1785781966
X-Ratelimit-Resource: core
```

| Mode | `X-Ratelimit-Remaining` on the refusal | Meaning | Response |
|---|---|---|---|
| Velocity | non-zero (4948 of 5000 in the readings above) | request rate, not quota | back off about 60 seconds, retry once |
| Exhaustion | `0`, with `X-Ratelimit-Resource` naming the bucket | the bucket really is drained | sleep until `X-Ratelimit-Reset`, then proceed |

In the exhaustion reading above, the reset epoch decoded to 11:32:46 PDT, two
and a half minutes out. Sleeping to that timestamp and issuing one call returned
`rjmurillo` on the first try. No polling, no retry loop, no re-auth.

The two instruments can contradict each other on the same named bucket, not
merely describe different ones. Measured 2026-08-05, 94 seconds apart:

```text
10:13:48Z  gh api rate_limit   ->  core: remaining=4829/5000
10:15:22Z  gh api user -i      ->  403, X-Ratelimit-Resource: core
                                        X-Ratelimit-Remaining: 0
                                        X-Ratelimit-Used: 5001
```

Both readings name `core`. One reports the bucket 96 percent free, the other
reports it over-drained by one call. So the payload is not lagging by a few
hundred calls, it is accounting for something other than the caller's own
budget. Treat a healthy `core` figure in that payload as carrying no
information about a `core` call, not as a stale version of the truth.

So the earlier advice not to reconcile against `rate_limit` still stands, and for
the reason already given: that endpoint is exempt and reports a bucket state that
does not describe your call. It is the wrong instrument, not a broken one. The
right instrument is the header on the response you were actually refused.

Do not infer the mode from how long the outage has lasted. Read the header.

## Two costs worth avoiding

`gh pr list --json statusCheckRollup --limit 100` returns `HTTP 504: We couldn't
respond to your request in time` against this repository. The check-rollup
expansion over that many pull requests exceeds GitHub's GraphQL time budget.
Split it: fetch `number,mergeStateStatus,isDraft,title` for the whole list, then
fetch `statusCheckRollup` per pull request only for the ones you need.

`mergeStateStatus` comes back `UNKNOWN` on a first query because GitHub computes
mergeability lazily. The first query enqueues the computation. Wait about a
minute and query again rather than treating `UNKNOWN` as a state. In one reading
48 of 55 were `UNKNOWN` on the first pass and 0 on the second.

## The blast radius reaches other people's CI

Measured 2026-08-04. The AI PR quality gate builds each agent's review context
by fetching the PR diff, and it authenticates as `user ID 6811113`, which is
`rjmurillo`. An interactive agent session authenticates as the same account.
They share one REST budget and one GraphQL budget.

On PR #4567, run `30929337949`, every one of the ten review agents failed at the
context step:

```
##[error]Failed to fetch PR diff for #4567 ... HTTP 403: API rate limit
exceeded for user ID 6811113
PR diff has 0 lines
##[error]Process completed with exit code 3.
```

`scripts/ci/build_ai_review_context.py` has no retry, so one 403 ends the job.
The remaining steps skip, `INFRA_FAILURE` is written as `false`, the verdict
comes back empty, and the required `Aggregate Results` check goes red while
every underlying job reports success. Issue #4547 tracks both halves.

Half of that landed. Re-measured 2026-08-05 on PR #4598, run `30988215939`:
the classification half is fixed and the retry half is not. The file grew from
424 to 515 lines, line 325 names issue #4547, and lines 247 to 252 match the
`rate limit|secondary rate|abuse detection` signature, so the 403 is now
classified as an infrastructure failure. The run recorded `INFRA_FAILURE: true`
and added the `infrastructure-failure` label. Re-running the issue's own grep,
`grep -nE "retry|retries|sleep|backoff|403|rate.?limit"`, still returns no
retry logic: all five hits are the rate-limit signature and its comments.

So the outcome is unchanged for the author. All ten agents logged
`retries: 0` and the PR is still blocked, because the step named "Invoke
Copilot CLI (with retry for infrastructure failures)" is *skipped* by the
infra gate rather than retried. A retry attached to the invocation cannot fire
for a failure that happens before the invocation. Check `retries: 0` in the
aggregate log to tell "retried and failed" from "never retried".

The consequence that is easy to miss: this is not confined to the PR the agent
is working on. Ten agents fetch a diff per run, so an agent polling `gh` across
a queue can drain the shared budget and turn *unrelated* PRs red. Nine or ten
identical `NEEDS_REVIEW` verdicts across independent agents is that signature,
not nine findings.

So throttle polling when a queue is in flight, prefer one paginated REST call
over repeated `gh pr checks`, and read a uniform verdict sweep as infrastructure
before reading it as review feedback.

## Re-running the failed jobs does not clear it

The obvious recovery is `gh run rerun <id> --failed`, and on this workflow it
cannot work. GitHub replays the jobs that already succeeded instead of running
them again, and the ten review jobs *did* succeed: the 403 poisoned their
output, not their exit status. So the aggregate re-reads the same empty
verdicts and fails identically.

Measured on run `30929337949` (PR #4567, 2026-08-04). Attempt 1 failed with
nine `NEEDS_REVIEW`. Attempt 2 failed with the same nine. The tell is in
`started_at`: the review rows still read 16:30 while the aggregate ran at
17:09, a 39 minute gap that no re-execution would produce.

Re-run the whole workflow instead:

```bash
gh run rerun <run_id>          # no --failed
```

Two traps around that command:

- **It prints nothing on success.** An empty response is not a failure. Confirm
  with `gh api repos/<owner>/<repo>/actions/runs/<id> --jq .run_attempt` and
  look for the number to increase.
- **Check the budget first.** Re-running into a drained budget just spends ten
  more agent jobs to reproduce the same red. Read
  `.resources.graphql.remaining` and, when it is low,
  `(.reset - now)` for the seconds to wait, before triggering anything.

## Git keeps working when the API does not

Measured 2026-08-05. Three consecutive `gh api` calls were refused with "API
rate limit exceeded for user ID 6811113" while `core` read 4785. In the same
window, against the same remote:

```
$ git fetch origin main        # exit 0, refs updated
$ git ls-remote origin main    # 5ec85be51aad2245...
$ git push origin HEAD:<branch>  # exit 0, new branch created
```

REST and GraphQL exhaustion does not touch the git transport. They are separate
services with separate limits.

So a rate limit does not stop work. Commit, merge, fetch, push, and run tests
during the outage. Only issue and pull request metadata is blocked. Do not idle
waiting for the bucket, and do not treat a refused `gh` call as a signal to
stop.

One trap that follows: `git ls-remote` reads the server, so it is the right
instrument for "did my push land". A push in this repository runs the full
Lefthook pre-push suite and takes 15 minutes or more. An empty `ls-remote`
during that window means "not yet", not "failed". Re-check before re-pushing.
Tailing the push log has the same hazard, because the file is still being
written and the tail lands in the middle of hook output.

## The shared budget had a root cause, and it was one secret

`BOT_PAT` authenticates as `rjmurillo` (user ID `6811113`), not the
`rjmurillo-bot` service account (`250269933`) that ADR-026 Decision 5
specifies. Verified 2026-08-05:

```
$ gh api user --jq .id              # 6811113   (interactive session)
$ gh api users/rjmurillo-bot --jq .id  # 250269933
```

At measurement time, `.github/actions/ai-review/action.yml` "Build context"
set `GH_TOKEN` from `inputs.bot-pat`, and 22 sites matched
`bot-pat: ${{ secrets.BOT_PAT }}`. Name that pattern when citing the count: a
bare grep for `secrets.BOT_PAT` returns 56 hits across 12 files. That step's
403 named `6811113`.

Later on 2026-08-05, `origin/main` changed read paths to
`${{ inputs.github-token || github.token || inputs.bot-pat }}`. Repository reads
now prefer the runner token and no longer require the shared `BOT_PAT` budget.
Copilot calls and write operations still use `bot-pat` where their permissions
require it. Issue #4607 remains open.

The earlier shared-budget measurements describe historical behavior, not the
current read path. Do not design around that shared read budget as permanent.
