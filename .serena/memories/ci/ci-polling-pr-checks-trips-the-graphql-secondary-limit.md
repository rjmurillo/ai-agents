# Parallel agents polling PR checks tripped the GraphQL secondary limit with quota left

## What happened

During the 2026-10-11 sweep, several agents polled PR checks at the same time. GitHub's secondary rate limit on GraphQL tripped while the primary quota still showed about 4,670 of 5,000 remaining. Every GraphQL-backed PR script then failed for about 30 minutes.

## Reading the signal

A healthy primary budget does not predict service. The secondary limit keys on request velocity, so a quota check says nothing about it. This is the same family as `ci/github-rate-limit-payload-does-not-predict-service` and the secondary-limiter section of `process/process-gh-graphql-and-rest-budgets-are-separate`. The new facts here are the GraphQL path, the full-quota reading, and the 30 minute outage.

## Working rule from the sweep

Each agent polls no faster than every 3 minutes. REST calls kept working during the outage, so REST-backed reads are the fallback while GraphQL is blocked.

## Sources

- Sweep report from the 2026-10-11 parallel-agent run (observed, not re-measured).
- `process/process-gh-graphql-and-rest-budgets-are-separate`, lines 36 to 44, for the secondary-limit mechanism.
