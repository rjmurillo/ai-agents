# Jq: Filtering With Select

## Skill-JQ-004: Filtering with select()

**Statement**: Use `select(condition)` to filter array elements; combine with `any()` for label/array matching.

**Pattern**:

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

**Atomicity**: 95%

---

## Related

- [jq-001-basic-field-extraction](jq-001-basic-field-extraction.md)
- [jq-002-raw-output-mode](jq-002-raw-output-mode.md)
- [jq-003-object-construction](jq-003-object-construction.md)
- [jq-005-array-operations](jq-005-array-operations.md)
- [jq-006-string-interpolation](jq-006-string-interpolation.md)
