# Agent API spend fails the required review check

Agents and CI draw on the SAME GitHub API budget, so heavy agent usage makes
pull requests fail a REQUIRED check. The loop is closed and measured, not
inferred.

## The loop

1. Agents burn the shared 5000/hr REST budget and the separate, smaller GraphQL
   budget.
2. CI's `scripts/ci/build_ai_review_context.py` calls `gh pr diff`, which is
   GraphQL, on that same exhausted budget.
3. The call fails, so the Copilot review step never runs.
4. `Aggregate Results` reports `DID_NOT_RUN`, and treats that as an explicit
   BLOCKING verdict.
5. `Aggregate Results` is one of the 17 required status checks, so the pull
   request cannot merge.

The spending that produces pull requests is what stops those pull requests from
landing. More parallel agents therefore reduce landing throughput past a point,
rather than increasing it.

## Measurement

Sampled 59 open pull request heads on 2026-08-05: 25 `Aggregate Results`
failures, 14 of them `DID_NOT_RUN`. A rerun with NO code change turned one
green (job 92318117514), which is the signature of an environmental failure
rather than a code failure.

## How to recognize it

A check that goes red on a transient error and green on rerun with no code
change is measuring the weather, not the code. `DID_NOT_RUN` on
`Aggregate Results` across many unrelated pull requests at once is the tell:
unrelated changes do not fail for the same reason simultaneously unless the
cause is shared infrastructure.

## The codebase half-knew

`scripts/ci/build_ai_review_context.py:190` carries a comment saying `gh pr
diff` goes through GraphQL and fails in the same quota window. The hazard was
documented and never handled. A comment that explains why a failure is
acceptable is a strong grep target for this class.

## The fix has two layers

Immediate: give the read steps a token that does not compete with the shared
budget. PR #4648 changes `.github/actions/ai-review/action.yml` read steps to
`inputs.github-token || github.token || inputs.bot-pat`, leaving the WRITE step
on bot-pat so review comments still post as the bot.

Hazard in that fix: `github.token` scopes come from the calling job's
`permissions:` block, not from repository settings. A present-but-underscoped
token is non-empty, so the `||` chain will NOT fall through, and the call fails
403 for a different reason. Verify every caller grants `pull-requests: read`.

Durable: separate three outcomes the code collapses into one. RAN-found-problems
blocks. RAN-found-nothing passes. COULD-NOT-RUN is not a verdict at all. Do NOT
make COULD-NOT-RUN pass; that trades a false red for a false green, and nobody
investigates a green.

## Operating rule while a fleet is running

Prefer REST over GraphQL. `gh pr view`, `gh pr diff`, `gh pr list`,
`gh pr checks`, `gh pr merge`, `gh pr create`, and `gh issue list --json` are
all GraphQL. Use git protocol where it answers the question at zero cost:
`git ls-remote` for push landing, `git log origin/main --oneline | grep '(#N)'`
for merge status, `git merge-tree --write-tree` for conflict prediction.

Read `X-RateLimit-Remaining` from `gh api -i` response headers. The
`/rate_limit` endpoint is advisory and disagreed with the enforcing limiter by
the entire budget in one measurement, with reset timestamps four minutes apart.

## References

- Issues #4547, #4607 (token budget), #4503 (independently green does not compose)
- PR #4648
- `.serena/memories/ci/github-rate-limit-payload-does-not-predict-service.md`
- `.serena/memories/process/process-gh-graphql-and-rest-budgets-are-separate.md`
