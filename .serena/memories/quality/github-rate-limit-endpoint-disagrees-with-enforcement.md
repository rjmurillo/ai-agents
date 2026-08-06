# The GitHub rate_limit endpoint disagrees with the limiter that enforces

## The claim this overturns

"To find out whether you are rate limited, ask `GET /rate_limit`." That is the
documented approach and the obvious one. It is unreliable, and its failure mode
is the dangerous direction: it reports headroom while every call is being
refused.

Measured in this repository with thirty agents sharing one token. Three probes,
six seconds apart, identical every time:

```text
real REST response headers      X-Ratelimit-Remaining: 0
                                X-Ratelimit-Used:      5000
                                X-Ratelimit-Resource:  core
                                X-Ratelimit-Reset:     08:33:52Z
                                HTTP 403

same moment, GET /rate_limit    core remaining=4792
                                core used=208
                                core reset=08:37:54Z
```

The two sources disagreed by the entire budget, 4792 against 0, and reported
reset timestamps four minutes apart. Repeated probes moved the endpoint's
counter (208, 209, 210) while the header stayed pinned at 0, so this is not a
race, a cache lag, or a transient. Two different buckets are being reported and
the one the endpoint shows is not the one that enforces.

## Why the error message does not help

The 403 body reads "API rate limit exceeded for user ID NNNNN", which sounds
like primary quota exhaustion. The body also links the Terms of Service section
on scraping, which is secondary-limiter language. Text alone cannot tell you
which limit you hit, so do not branch on the message.

## What to run instead

Read the headers of a real response. They come from the edge that refused you.

```bash
gh api -i "repos/OWNER/REPO/issues?per_page=1" 2>/dev/null \
  | grep -iE '^X-Ratelimit-(Remaining|Used|Resource|Reset):'
```

Rules that follow:

- Treat `GET /rate_limit` as advisory. Never gate on it alone.
- When the header and the endpoint disagree, believe the header.
- Honor the header's reset. The endpoint's reset belongs to the other bucket.
- If you must reconcile both, take the more pessimistic value. It is cheap and
  correct under either mechanism.

## Consequence for any gate built on the endpoint

A health check that reads only `GET /rate_limit` does not merely fail to see
some failure modes. It is affirmatively wrong about the main one, because it
returns a healthy number during a total outage. Reporting a single boolean makes
this worse by collapsing "cannot determine" onto "fine". Return three states,
OK, LIMITED, and UNKNOWN, and require callers to handle UNKNOWN as not-OK. See
`quality/add-missing-state-not-sentinel` for the general shape.

## What still works during the outage

Git protocol is unaffected and costs no quota. Verified during a full REST
outage: `git ls-remote origin HEAD` returned the expected sha while every REST
call returned 403.

```bash
git ls-remote origin <branch>      # did my push land
git log origin/main --oneline -50  # what merged, squash subjects carry (#NNNN)
git fetch origin '+refs/pull/*/head:refs/remotes/pr/*'
git merge-tree --write-tree origin/main <head>   # true mergeability
```

Most verification work has a git-protocol equivalent that is both free and more
authoritative than the API answer.

## Do not make it worse

Concurrent retries extend the window rather than shortening it. One retry after
a real wait, never a poll. Prefer REST over anything routed through GraphQL:
`gh pr create`, `gh pr view`, `gh pr diff`, `gh pr list`, `gh pr checks`,
`gh pr merge`, and `gh issue list --json` all use GraphQL, which carries a
separate and usually more burned budget. Never pass `--paginate`.
