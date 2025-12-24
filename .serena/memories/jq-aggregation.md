# jq: Aggregation

## Skill-JQ-008

**Statement**: Use `add`, `min`, `max`, `length` for aggregating array data.

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
