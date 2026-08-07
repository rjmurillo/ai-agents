# A duplicate check that searches issues only is half a check

## The rule

Before filing a fix, search **open pull requests** as well as issues. A fix that is already
in flight lives in a PR, not in an issue, and an `is:issue` qualifier makes that PR
invisible.

## What it cost

Diagnosed a merge-tree ratchet failure, wrote the fix, wrote a guard, proved the guard
failed without the fix, and opened PR #4582. PR #4572 was already open and was a strict
superset: it closed the same `actions/checkout` site plus seven `git fetch --depth=` sites,
scanned every workflow instead of one job, and proved the mechanism against real git
repositories.

The duplicate check that missed it was:

```text
repo:rjmurillo/ai-agents+is:issue+bot-skip+checkout+shallow
repo:rjmurillo/ai-agents+is:issue+Renovate+merge-tree
repo:rjmurillo/ai-agents+is:issue+fetch-depth+bot
```

Three queries, all correct, all blind to the thing that mattered. The searches returned the
closed issue whose incomplete fix started the whole investigation, which made the results
look thorough.

## Why the failure feels like success

Searching issues answers "has anyone *reported* this". Filing a fix requires the answer to
"is anyone *fixing* this". Those are different questions, and only the second one prevents
duplicated work. A rich issue-search result is not evidence about the second question.

## The check

Run both, and treat the PR search as the blocking one:

```bash
gh api "search/issues?q=repo:OWNER/REPO+is:issue+<terms>&per_page=5" \
  --jq '.items[]|"#\(.number) [\(.state)] \(.title)"'
gh api "search/issues?q=repo:OWNER/REPO+is:pr+is:open+<terms>&per_page=5" \
  --jq '.items[]|"#\(.number) [\(.state)] \(.title)"'
```

Search terms should name the **mechanism**, not the symptom. `merge base`, `shallow`, and
`fetch-depth` would each have surfaced #4572 by title; the symptom-shaped terms did not.

When title search is thin, list open PRs and read the titles directly. At 45 open PRs the
full list is one API call and scanning it takes under a minute, which is far cheaper than a
wasted branch, guard, push, and review cycle.

## Related

`process/process-gh-graphql-and-rest-budgets-are-separate` covers running these searches
when GraphQL is exhausted: `gh search issues` is GraphQL and dies at zero, while
`gh api search/issues?q=` is REST and keeps working.
