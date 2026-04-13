# Jq: Raw Output Mode

## Skill-JQ-002: Raw Output Mode

**Statement**: Use `-r` flag to remove quotes from string output; essential for shell scripting.

**Pattern**:

```bash
# Without -r (includes quotes)
echo '{"name": "test"}' | jq '.name'
# Output: "test"

# With -r (raw strings)
echo '{"name": "test"}' | jq -r '.name'
# Output: test

# Use in shell scripts
TITLE=$(gh pr view 123 --json title --jq -r '.title')
echo "PR Title: $TITLE"

# Multiple values
gh issue list --json number,title --jq -r '.[] | "\(.number)\t\(.title)"'
```

**Atomicity**: 94%

---

## Related

- [jq-001-basic-field-extraction](jq-001-basic-field-extraction.md)
- [jq-003-object-construction](jq-003-object-construction.md)
- [jq-004-filtering-with-select](jq-004-filtering-with-select.md)
- [jq-005-array-operations](jq-005-array-operations.md)
- [jq-006-string-interpolation](jq-006-string-interpolation.md)
