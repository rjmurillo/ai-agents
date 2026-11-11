# EUREKA: maximum parallelism on one GitHub token slows the sweep, so cap PR drivers by API budget

## Question

A sweep has 34 issues and each PR needs polling, thread replies, and a merge. Does one agent per item finish sooner than a few at a time?

## Conventional answer

Agents are cheap and work is independent, so run them all at once. Wall-clock time drops with the number of agents.

## First-principles position

The agents are not independent. They share one token, and polling is the dominant API cost: every driver reads checks and threads many times before a PR merges.

Observed in the 2026-11-10 sweep:

- `get_pr_checks.py` waits for PR 7259 hit `gh: API rate limit already exceeded for user ID NNNNN` on GraphQL, retried three times, and ended with `Timeout: 2 check(s) still pending after 560 seconds` (local file `checks_7259.txt`, 2026-11-10 evening).
- The sweep log estimates about 31 concurrent agents and says the 5000 per hour budget was gone in roughly one hour. That count and duration are REPORTED, not timestamped.
- The log also says drivers stalled on reset timers, and at least one ended its turn to wait with nothing to wake it.
- REST kept working while the GraphQL bucket was refused, so `gh pr view`, `gh pr checks`, and `gh pr list` (all GraphQL) are the calls most at risk (INFERRED from the existing rate-limit memory, not measured per command).

Once the budget is gone, every agent stops, including those with a merge-ready PR. The sweep then waits on a clock no agent controls.

This is the second time. The 2026-10-11 sweep exhausted `/tmp` inodes with about 12 agents. The cap of 4 concurrent delegations is written in `templates/agents/orchestrator.shared.md` (line 329 on `origin/main`, 2026-11-11), and a hand-written brief carried neither it nor any API budget rule. See the wave-cap memory.

## What to do

1. Read the budget before each wave: `gh api graphql -f query='{ rateLimit { remaining resetAt } }'`.
2. Cap concurrent PR drivers by remaining budget and expected polls per PR. Drivers use bounded waits inside the skill scripts, never a polling loop.
3. Put the cap and the wait rule in the brief itself. A cap that lives only in a template did not bind a hand-written brief twice.
4. A child that must wait starts a background job. A finished turn has nothing to wake it.

The right number is not measured here. The only measured fact is that about 30 was too many for one token.

## Relations

- **related_to**: [orchestration/orchestration-the-wave-cap-lives-in-the-orchestrator-template-not-in-a-hand-written-brief](orchestration/orchestration-the-wave-cap-lives-in-the-orchestrator-template-not-in-a-hand-written-brief.md)
- **related_to**: [quality/github-rate-limit-endpoint-disagrees-with-enforcement](quality/github-rate-limit-endpoint-disagrees-with-enforcement.md)
- **related_to**: [ci/github-rate-limit-payload-does-not-predict-service](ci/github-rate-limit-payload-does-not-predict-service.md)
