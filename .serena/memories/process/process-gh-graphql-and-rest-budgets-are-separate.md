# `gh issue list` and `gh api` draw on different rate-limit budgets, and `--paginate` trips a third limiter

## Question

A large agent fleet exhausts the GitHub API and `gh issue list` starts
returning `API rate limit already exceeded`. Is the only option to wait for the
reset?

## Conventional answer

Yes. The budget is exhausted, the reset time is published, wait for it. Sharing
one token across many workers means the whole fleet stalls together.

## First-principles position

No. GitHub meters **three** budgets independently, and `gh` subcommands are not
all on the same one.

- `gh issue list`, `gh pr list`, `gh issue view`, `gh pr view`, and
  `gh pr create` go through **GraphQL**, which has its own 5000-point budget.
- `gh api /repos/...` on a REST path draws on the **core** REST budget, a
  separate 5000 requests.
- `gh search` draws on the **search** budget, 30 per minute.

Exhausting one leaves the others untouched. Measured live during this incident:

```json
{"core":    {"limit":5000,"remaining":4895,"used":105},
 "graphql": {"limit":5000,"remaining":0,   "used":5002}}
```

GraphQL was empty with 30 minutes to reset. REST core was 98 percent full. The
fleet did not need to stall at all; it needed to change which endpoint it
called.

There is a fourth limiter that is not a budget. GitHub applies a **secondary
rate limit** to bursts of concurrent requests, and it returns HTTP 403 with the
same "API rate limit exceeded" wording even when the primary budget is nearly
untouched. `gh api --paginate` fires its pages back to back and trips it: the
paginated call 403'd after five pages while a single call to page 1 of the same
endpoint immediately afterward returned 100 results.

So the error string is ambiguous across three distinct causes: primary GraphQL
exhaustion, primary REST exhaustion, and secondary burst throttling. The remedy
differs for each and the message does not tell you which one you hit.

## Evidence

Observed 2026-08-02 with roughly twenty concurrent agents sharing one token.

1. `gh issue list --state open --limit 400` failed:
   `GraphQL: API rate limit already exceeded for user ID`.
2. `gh api rate_limit` showed graphql 0 of 5000, core 4934 of 5000.
3. `gh api --paginate '/repos/rjmurillo/ai-agents/issues?state=open&per_page=100'`
   returned five lines then HTTP 403.
4. `gh api '/repos/rjmurillo/ai-agents/issues?state=open&per_page=100&page=1'`
   returned 100 immediately, with core still at 4895.
5. Manual pagination with `sleep 3` between pages completed cleanly: 137 open
   items across two pages.

## Decision

When a `gh` command reports a rate limit:

1. Run `gh api rate_limit` first and read which budget is actually empty.
   Do not infer it from the message.
2. If GraphQL is empty and core is not, switch to REST:
   - issue body and metadata: `gh api /repos/OWNER/REPO/issues/NNNN`
   - issue comments: `gh api /repos/OWNER/REPO/issues/NNNN/comments`
   - pull request: `gh api /repos/OWNER/REPO/pulls/NNNN`
   - review comments: `gh api /repos/OWNER/REPO/pulls/NNNN/comments`
   - create a PR: `gh api -X POST /repos/OWNER/REPO/pulls --input body.json`
3. Never use `gh api --paginate` from a fleet. Page manually with
   `&page=N&per_page=100` and `sleep 3` between pages.

Note that `/repos/OWNER/REPO/issues` returns pull requests as well as issues.
Discriminate on the `pull_request` key rather than issuing two calls.
