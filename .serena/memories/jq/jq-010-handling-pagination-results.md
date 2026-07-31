# Jq: Handling Pagination Results

## Skill-JQ-010: Handling Pagination Results

**Statement**: Use `--slurp` with `--paginate` to combine paginated results into a single array.

**Pattern**:

```bash
# Without slurp (separate arrays per page)
gh api --paginate repos/{owner}/{repo}/issues
# Output: [{...}] [{...}] [{...}]

# With slurp (single combined array)
gh api --paginate --slurp repos/{owner}/{repo}/issues --jq 'flatten'
# Output: [{...}, {...}, {...}]

# Count all results
gh api --paginate --slurp repos/{owner}/{repo}/issues --jq 'flatten | length'

# Filter across all pages
gh api --paginate --slurp repos/{owner}/{repo}/issues \
  --jq 'flatten | [.[] | select(.labels | any(.name == "bug"))]'

# GraphQL pagination result handling
gh api graphql --paginate -f query='...' \
  --jq '.data.repository.issues.nodes'
```

**Atomicity**: 93%

---

## Common jq Pitfalls

### Pitfall-JQ-001: Forgetting Raw Mode

**Problem**: Quotes in output break shell scripts.

```bash
# BAD
TITLE=$(gh pr view 123 --json title --jq '.title')
# TITLE="My PR" (with quotes)

# GOOD
TITLE=$(gh pr view 123 --json title --jq -r '.title')
# TITLE=My PR (without quotes)
```

### Pitfall-JQ-002: Null Values in Pipelines

**Problem**: Null values can cause unexpected behavior.

```bash
# BAD - fails if milestone is null
gh issue list --json milestone --jq '.[].milestone.title'

# GOOD - handle nulls
gh issue list --json milestone --jq '.[].milestone.title // "None"'

# GOOD - filter nulls first
gh issue list --json milestone --jq '[.[] | select(.milestone != null)] | .[].milestone.title'
```

### Pitfall-JQ-003: Type Mismatches

**Problem**: Comparing different types silently fails.

```bash
# BAD - comparing number to string
echo '{"count": 5}' | jq 'select(.count == "5")'  # No match

# GOOD - consistent types
echo '{"count": 5}' | jq 'select(.count == 5)'   # Matches
echo '{"count": "5"}' | jq 'select(.count == "5")' # Matches

# GOOD - convert types
echo '{"count": "5"}' | jq 'select((.count | tonumber) == 5)'
```

### Pitfall-JQ-004: Array vs Object Context

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

---

## Quick Reference

The operator, filter, string, and type tables live in one place:
[jq-quick-reference](jq-quick-reference.md). They used to be duplicated here,
which let the two copies drift and forced every fix to be applied twice.

---

## Related

- [jq-001-basic-field-extraction](jq-001-basic-field-extraction.md)
- [jq-002-raw-output-mode](jq-002-raw-output-mode.md)
- [jq-003-object-construction](jq-003-object-construction.md)
- [jq-004-filtering-with-select](jq-004-filtering-with-select.md)
- [jq-005-array-operations](jq-005-array-operations.md)
- [jq-quick-reference](jq-quick-reference.md)
