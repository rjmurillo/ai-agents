# jq: Conditional Logic

## Skill-JQ-007

**Statement**: Use `if-then-else` for conditional values; `//` for defaults.

```bash
# If-then-else
gh pr list --json number,draft \
  --jq '.[] | {number, status: (if .draft then "Draft" else "Ready" end)}'

# Default values (null coalescing)
gh issue list --json number,milestone \
  --jq '.[] | {number, milestone: (.milestone.title // "No Milestone")}'

# Alternative operator
gh api repos/{owner}/{repo} --jq '.description // "No description"'

# Multiple fallbacks
gh pr view 123 --json body --jq '.body // .title // "Untitled"'

# Type-based conditionals
gh api repos/{owner}/{repo}/contents \
  --jq '.[] | if .type == "dir" then "DIR: \(.name)" else "FILE: \(.name)" end'
```
