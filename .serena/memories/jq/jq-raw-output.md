# jq: Raw Output Mode

## Skill-JQ-002

**Statement**: Use `-r` flag to remove quotes from string output; essential for shell scripting. Applies to external `jq`. The `gh --jq` built-in is already raw and rejects `-r`.

```bash
# Without -r (includes quotes)
echo '{"name": "test"}' | jq '.name'
# Output: "test"

# With -r (raw strings)
echo '{"name": "test"}' | jq -r '.name'
# Output: test

# gh's built-in --jq is already raw and takes exactly one argument,
# so it needs no -r and exits 1 if you pass one.
TITLE=$(gh pr view 123 --json title --jq '.title')
echo "PR Title: $TITLE"

# Multiple values
gh issue list --json number,title --jq '.[] | "\(.number)\t\(.title)"'
```

## Related

- [jq-aggregation](jq-aggregation.md)
- [jq-array-operations](jq-array-operations.md)
- [jq-conditionals](jq-conditionals.md)
- [jq-field-extraction](jq-field-extraction.md)
- [jq-filtering](jq-filtering.md)
