# jq: Common Pitfalls

## Pitfall-JQ-001: Raw Mode Belongs to External jq, Not `--jq`

**Problem**: Quotes in output break shell scripts, but the fix depends on which
jq is doing the work.

`gh`'s built-in `--jq` already emits raw output for string results, and it takes
exactly one argument, so passing `-r` to it is a syntax error rather than an
improvement. External `jq` is the one that quotes strings by default and needs
`-r`.

```bash
# gh's built-in --jq: already raw
TITLE=$(gh pr view 123 --json title --jq '.title')
# TITLE=My PR

# ...and -r is a syntax error, not a fix
gh pr view 123 --json title --jq -r '.title'
# accepts at most 1 arg(s), received 2

# External jq: quotes by default
gh pr view 123 --json title | jq '.title'
# "My PR"

# External jq: -r strips them
gh pr view 123 --json title | jq -r '.title'
# My PR
```

All four forms measured against gh 2.96.0.

## Pitfall-JQ-002: Null Values in Pipelines

**Problem**: Null values can cause unexpected behavior.

```bash
# BAD - fails if milestone is null
gh issue list --json milestone --jq '.[].milestone.title'

# GOOD - handle nulls
gh issue list --json milestone --jq '.[].milestone.title // "None"'

# GOOD - filter nulls first
gh issue list --json milestone --jq '[.[] | select(.milestone != null)] | .[].milestone.title'
```

## Pitfall-JQ-003: Type Mismatches

**Problem**: Comparing different types silently fails.

```bash
# BAD - comparing number to string
echo '{"count": 5}' | jq 'select(.count == "5")'  # No match

# GOOD - consistent types
echo '{"count": 5}' | jq 'select(.count == 5)'   # Matches

# GOOD - convert types
echo '{"count": "5"}' | jq 'select((.count | tonumber) == 5)'
```

## Pitfall-JQ-004: Array vs Object Context

**Problem**: Using array operators on objects or vice versa.

```bash
# BAD - .[] on object gives values only
echo '{"a": 1, "b": 2}' | jq '.[]'
# Output: 1 2 (loses keys)

# GOOD - use to_entries for key-value pairs
echo '{"a": 1, "b": 2}' | jq 'to_entries | .[] | "\(.key)=\(.value)"'
# Output: "a=1" "b=2"

# GOOD - keys only
echo '{"a": 1, "b": 2}' | jq 'keys'
# Output: ["a", "b"]
```

## Related

- [jq-aggregation](jq-aggregation.md)
- [jq-array-operations](jq-array-operations.md)
- [jq-conditionals](jq-conditionals.md)
- [jq-field-extraction](jq-field-extraction.md)
- [jq-filtering](jq-filtering.md)
