# jq JSON Parsing Skills

## Overview

Patterns and skills for using jq to parse JSON output from GitHub CLI and REST API responses. Essential for automation scripts and CI/CD pipelines.

**Last Updated**: 2025-12-18

---

## Skill-JQ-001: Basic Field Extraction

**Statement**: Use `.field` syntax for object access; `.[]` for array iteration.

**Pattern**:

```bash
# Single field
echo '{"name": "test"}' | jq '.name'
# Output: "test"

# Nested field
echo '{"user": {"login": "octocat"}}' | jq '.user.login'
# Output: "octocat"

# Array iteration
echo '[{"id": 1}, {"id": 2}]' | jq '.[].id'
# Output:
# 1
# 2

# Specific array index
echo '[{"id": 1}, {"id": 2}]' | jq '.[0]'
# Output: {"id": 1}
```

**Atomicity**: 95%

---

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

## Skill-JQ-006: String Interpolation

**Statement**: Use `\(.field)` inside strings for template-style output.

**Pattern**:

```bash
# Basic interpolation
gh pr list --json number,title \
  --jq -r '.[] | "#\(.number): \(.title)"'
# Output: #123: Fix bug

# Multi-field formatting
gh issue list --json number,title,state \
  --jq -r '.[] | "[\(.state)] #\(.number) - \(.title)"'

# With conditionals
gh pr list --json number,draft \
  --jq -r '.[] | "#\(.number) \(if .draft then "(DRAFT)" else "" end)"'

# Building URLs
gh pr list --json number \
  --jq -r '.[] | "https://github.com/owner/repo/pull/\(.number)"'

# Tab-separated for shell parsing
gh issue list --json number,title,state \
  --jq -r '.[] | "\(.number)\t\(.title)\t\(.state)"'
```

**Atomicity**: 93%

---

## Skill-JQ-007: Conditional Logic

**Statement**: Use `if-then-else` for conditional values; `//` for defaults.

**Pattern**:

```bash
# If-then-else
gh pr list --json number,draft \
  --jq '.[] | {number, status: (if .draft then "Draft" else "Ready" end)}'

# Default values (null coalescing)
gh issue list --json number,milestone \
  --jq '.[] | {number, milestone: (.milestone.title // "No Milestone")}'

# Alternative operator
gh api repos/{owner}/{repo} --jq '.description // "No description"'

# Multiple fallbacks
gh pr view 123 --json body --jq '.body // .title // "Untitled"'

# Type-based conditionals
gh api repos/{owner}/{repo}/contents \
  --jq '.[] | if .type == "dir" then "DIR: \(.name)" else "FILE: \(.name)" end'
```

**Atomicity**: 92%

---

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

## Skill-JQ-009: GitHub CLI Integration Patterns

**Statement**: Combine `--json` with `--jq` for efficient data extraction directly in gh commands.

**Pattern**:

```bash
# Inline jq with gh
gh pr list --json number,title --jq '.[0].title'

# Complex filtering
gh issue list --json number,labels,state \
  --jq '[.[] | select(.state == "open") | select(.labels | any(.name == "bug"))] | length'

# Building reports
gh pr list --state all --json number,mergedAt,author \
  --jq '[.[] | select(.mergedAt != null)] | group_by(.author.login) |
        map({author: .[0].author.login, merged: length}) |
        sort_by(.merged) | reverse'

# Extracting for shell variables
PR_COUNT=$(gh pr list --state open --json number --jq 'length')
echo "Open PRs: $PR_COUNT"

# CSV output
gh issue list --json number,title,state \
  --jq -r '["number","title","state"], (.[] | [.number, .title, .state]) | @csv'

# TSV output
gh pr list --json number,title \
  --jq -r '.[] | [.number, .title] | @tsv'
```

**Atomicity**: 95%

---

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

### Basic Operators

| Operator | Purpose | Example |
|----------|---------|---------|
| `.field` | Access field | `.name` |
| `.[]` | Iterate array | `.[].id` |
| `.[n]` | Index array | `.[0]` |
| `\|` | Pipe | `.[] \| .name` |
| `,` | Multiple outputs | `.name, .id` |

### Filters

| Function | Purpose | Example |
|----------|---------|---------|
| `select()` | Filter | `select(.state == "open")` |
| `map()` | Transform | `map(.name)` |
| `sort_by()` | Sort | `sort_by(.date)` |
| `group_by()` | Group | `group_by(.author)` |
| `unique` | Dedupe | `unique` |
| `flatten` | Flatten arrays | `flatten` |

### String Functions

| Function | Purpose | Example |
|----------|---------|---------|
| `contains()` | Substring match | `select(.name \| contains("api"))` |
| `startswith()` | Prefix match | `select(.name \| startswith("test"))` |
| `split()` | Split string | `split(",")` |
| `join()` | Join array | `join(", ")` |
| `@csv` | CSV format | `[.a, .b] \| @csv` |
| `@tsv` | TSV format | `[.a, .b] \| @tsv` |

### Type Functions

| Function | Purpose | Example |
|----------|---------|---------|
| `type` | Get type | `type` |
| `tonumber` | To number | `.count \| tonumber` |
| `tostring` | To string | `.id \| tostring` |
| `length` | Array/string length | `length` |
| `keys` | Object keys | `keys` |

---

## Related Memories

- `skills-github-cli.md` - GitHub CLI command patterns
- `github-rest-api-reference.md` - API endpoint reference

## References

- [jq Manual](https://jqlang.github.io/jq/manual/)
- [jq Tutorial](https://jqlang.org/tutorial/)
- [jq Cookbook](https://github.com/stedolan/jq/wiki/Cookbook)
