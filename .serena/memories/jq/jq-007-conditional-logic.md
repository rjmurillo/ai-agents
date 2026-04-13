# Jq: Conditional Logic

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

## Related

- [jq-001-basic-field-extraction](jq-001-basic-field-extraction.md)
- [jq-002-raw-output-mode](jq-002-raw-output-mode.md)
- [jq-003-object-construction](jq-003-object-construction.md)
- [jq-004-filtering-with-select](jq-004-filtering-with-select.md)
- [jq-005-array-operations](jq-005-array-operations.md)
