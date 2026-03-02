# Jq: Object Construction

## Skill-JQ-003: Object Construction

**Statement**: Use `{key: .path}` to create new objects with selected fields.

**Pattern**:

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

**Atomicity**: 93%

---

## Related

- [jq-001-basic-field-extraction](jq-001-basic-field-extraction.md)
- [jq-002-raw-output-mode](jq-002-raw-output-mode.md)
- [jq-004-filtering-with-select](jq-004-filtering-with-select.md)
- [jq-005-array-operations](jq-005-array-operations.md)
- [jq-006-string-interpolation](jq-006-string-interpolation.md)
