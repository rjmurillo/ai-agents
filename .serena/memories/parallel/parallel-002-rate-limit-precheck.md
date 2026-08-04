# Skill-Parallel-002: Rate Limit Pre-Check

## Statement

Before launching parallel operations that make GitHub API calls, check rate limit and reserve budget to prevent exhaustion during execution.

## Atomicity Score: 92%

## Impact: 9/10

## Context

Applies before:

- Launching parallel agents
- Batch PR operations
- Automated workflows making multiple API calls
- Any operation where multiple processes share rate limit

## Pattern

### Pre-flight Check

```bash
# Gate on GraphQL, not REST. REST is almost never the binding constraint.
# Measured during a live outage: REST core 4938 remaining while GraphQL was 0.
# A gate reading .rate.remaining reports "healthy" throughout that outage.
remaining=$(gh api rate_limit --jq '.resources.graphql.remaining')
reset_time=$(gh api rate_limit --jq '.resources.graphql.reset')

# Estimate required calls
num_agents=4
calls_per_agent=50  # Conservative estimate
required=$((num_agents * calls_per_agent))

# Check before proceeding
if [[ $remaining -lt $required ]]; then
  echo "ERROR: Insufficient rate limit"
  echo "  Remaining: $remaining"
  echo "  Required: $required"
  echo "  Resets at: $(date -d @$reset_time)"
  exit 1
fi

echo "Rate limit OK: $remaining remaining, need $required"
```

### Coordination Pattern

When multiple agents share rate limit:

1. Calculate total budget before launch
2. Divide budget per agent: `budget_per_agent=$((remaining / num_agents))`
3. Pass budget to agent prompts
4. Agent should exit when approaching budget

## GraphQL vs REST

```bash
# Check both limits
gh api rate_limit --jq '{
  rest: .rate.remaining,
  graphql: .resources.graphql.remaining,
  search: .resources.search.remaining
}'
```

GraphQL has separate limit (5000/hour) - relevant for review thread resolution.

## CI authenticates as the same user, so your polling reds unrelated PRs

In this repo the AI review gate and an interactive agent session are the **same
identity** (`user ID 6811113`, `rjmurillo`). They draw on one GraphQL budget.

One full AI gate run costs roughly **2250 GraphQL points**, so the 5000/hour
ceiling supports about **two gate runs per hour**, shared with everything else
on that identity. An agent fleet polling `gh pr list`, `gh pr view`, and
`gh api graphql` across a large PR queue therefore drains the budget the gate
needs, and the review jobs of **PRs you are not touching** 403 on their diff
fetch. Ten agents per run each fetch a diff, so the failure is broad.

The signature is distinctive: every individual review job reports success, all
ten agent verdicts come back `NEEDS_REVIEW` with 0-byte findings, and only the
required `Aggregate Results` row goes red. Identical verdicts across independent
agents are an infrastructure signature, not findings.

Recovery, in order:

1. Read `.resources.graphql.remaining` **before** re-running. Below ~2250 means
   wait `(.reset - now)` seconds. Re-running into a drained budget guarantees
   another red.
2. Re-run the **whole workflow** (`gh run rerun <id>`). `--failed` cannot clear
   it: the review jobs succeeded, so only the aggregate re-runs and it re-reads
   the same empty verdicts.
3. Confirm the re-run fired by watching `.run_attempt` increment. `gh run rerun`
   prints nothing on success.

Tracked by issue #4547.

## Warning Signs

- "API rate limit exceeded" errors during parallel execution
- CI workflows failing with 403
- Agents completing partially then stopping

## Evidence

Session 04 (2025-12-24): Launched 4 parallel agents without rate limit check. Each agent made 50+ API calls. No failures occurred (lucky), but risk was high.

## Related

- Memory: [github-cli-api-patterns](github-cli-api-patterns.md)
- Memory: [automation-priorities-2025-12](automation-priorities-2025-12.md) (rate limit coordination service)
- [parallel-001-worktree-isolation](parallel-001-worktree-isolation.md)

## Tags

- #rate-limit
- #parallel
- #github-api
- #coordination
