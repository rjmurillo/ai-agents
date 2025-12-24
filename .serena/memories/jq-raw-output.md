# jq: Raw Output Mode

## Skill-JQ-002

**Statement**: Use `-r` flag to remove quotes from string output; essential for shell scripting.

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
