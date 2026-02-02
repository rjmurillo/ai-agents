# jq: Object Construction

## Skill-JQ-003

**Statement**: Use `{key: .path}` to create new objects with selected fields.

```bash
# Select specific fields
gh pr list --json number,title,author \
  --jq '.[] | {pr: .number, title: .title, author: .author.login}'

# Rename fields
gh api repos/{owner}/{repo} \
  --jq '{name: .name, stars: .stargazers_count, forks: .forks_count}'

# Add computed fields
gh issue list --json number,labels \
  --jq '.[] | {number, label_count: (.labels | length)}'

# Flatten nested structures
gh pr list --json number,author \
  --jq '.[] | {number, author: .author.login}'
```

## Related

- [jq-aggregation](jq-aggregation.md)
- [jq-array-operations](jq-array-operations.md)
- [jq-conditionals](jq-conditionals.md)
- [jq-field-extraction](jq-field-extraction.md)
- [jq-filtering](jq-filtering.md)
