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
# Get current rate limit status
remaining=$(gh api rate_limit --jq '.rate.remaining')
reset_time=$(gh api rate_limit --jq '.rate.reset')

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

## Warning Signs

- "API rate limit exceeded" errors during parallel execution
- CI workflows failing with 403
- Agents completing partially then stopping

## Evidence

Session 04 (2025-12-24): Launched 4 parallel agents without rate limit check. Each agent made 50+ API calls. No failures occurred (lucky), but risk was high.

## Related

- Memory: [github-cli-api-patterns](github-cli-api-patterns.md)
- Memory: [automation-priorities-2025-12](automation-priorities-2025-12.md) (rate limit coordination service)

## Tags

- #rate-limit
- #parallel
- #github-api
- #coordination

## Related

- [parallel-001-worktree-isolation](parallel-001-worktree-isolation.md)
