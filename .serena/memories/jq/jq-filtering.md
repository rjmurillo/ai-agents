# jq: Filtering with select()

## Skill-JQ-004

**Statement**: Use `select(condition)` to filter array elements; combine with `any()` for label/array matching.

```bash
# Filter by field value
gh pr list --json number,state \
  --jq '.[] | select(.state == "open")'

# Filter by label
gh issue list --json number,labels \
  --jq '.[] | select(.labels | any(.name == "bug"))'

# Multiple conditions
gh pr list --json number,draft,mergeable \
  --jq '.[] | select(.draft == false and .mergeable == "MERGEABLE")'

# Numeric comparison
gh run list --json databaseId,createdAt \
  --jq '.[] | select(.databaseId > 1000000)'

# String matching
gh repo list --json name,description \
  --jq '.[] | select(.name | contains("api"))'

# Null handling
gh issue list --json number,milestone \
  --jq '.[] | select(.milestone != null)'
```

## Related

- [jq-aggregation](jq-aggregation.md)
- [jq-array-operations](jq-array-operations.md)
- [jq-conditionals](jq-conditionals.md)
- [jq-field-extraction](jq-field-extraction.md)
- [jq-github-cli-integration](jq-github-cli-integration.md)
