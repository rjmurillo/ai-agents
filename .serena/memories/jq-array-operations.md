# jq: Array Operations

## Skill-JQ-005

**Statement**: Use `map()`, `sort_by()`, `group_by()`, `unique` for array transformations.

```bash
# Map transformation
gh pr list --json number --jq '[.[] | .number]'

# Sort by field
gh release list --json tagName,publishedAt \
  --jq 'sort_by(.publishedAt) | reverse'

# Get first/last
gh release list --json tagName,publishedAt \
  --jq 'sort_by(.publishedAt) | last'

# Unique values
gh issue list --json labels \
  --jq '[.[].labels[].name] | unique'

# Group by field
gh pr list --json author,number \
  --jq 'group_by(.author.login) | map({author: .[0].author.login, count: length})'

# Flatten nested arrays
gh issue list --json labels \
  --jq '[.[].labels] | flatten | unique_by(.name)'

# Length/count
gh pr list --json number --jq 'length'
```

## Related

- [jq-aggregation](jq-aggregation.md)
- [jq-conditionals](jq-conditionals.md)
- [jq-field-extraction](jq-field-extraction.md)
- [jq-filtering](jq-filtering.md)
- [jq-github-cli-integration](jq-github-cli-integration.md)
