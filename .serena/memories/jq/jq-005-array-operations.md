# Jq: Array Operations

## Skill-JQ-005: Array Operations

**Statement**: Use `map()`, `sort_by()`, `group_by()`, `unique` for array transformations.

**Pattern**:

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

**Atomicity**: 94%

---

## Related

- [jq-001-basic-field-extraction](jq-001-basic-field-extraction.md)
- [jq-002-raw-output-mode](jq-002-raw-output-mode.md)
- [jq-003-object-construction](jq-003-object-construction.md)
- [jq-004-filtering-with-select](jq-004-filtering-with-select.md)
- [jq-006-string-interpolation](jq-006-string-interpolation.md)
