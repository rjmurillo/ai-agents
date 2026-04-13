# Jq: Aggregation

## Skill-JQ-008: Aggregation

**Statement**: Use `add`, `min`, `max`, `length` for aggregating array data.

**Pattern**:

```bash
# Count items
gh issue list --json number --jq 'length'

# Sum values
echo '[{"count": 5}, {"count": 3}]' | jq '[.[].count] | add'
# Output: 8

# Min/max
gh run list --json createdAt \
  --jq '[.[].createdAt] | min'

# Average
echo '[{"val": 10}, {"val": 20}]' | jq '[.[].val] | add / length'

# Count by group
gh pr list --json state \
  --jq 'group_by(.state) | map({state: .[0].state, count: length})'

# Boolean aggregation (all/any)
gh pr list --json mergeable \
  --jq '[.[].mergeable == "MERGEABLE"] | all'
```

**Atomicity**: 91%

---

## Related

- [jq-001-basic-field-extraction](jq-001-basic-field-extraction.md)
- [jq-002-raw-output-mode](jq-002-raw-output-mode.md)
- [jq-003-object-construction](jq-003-object-construction.md)
- [jq-004-filtering-with-select](jq-004-filtering-with-select.md)
- [jq-005-array-operations](jq-005-array-operations.md)
