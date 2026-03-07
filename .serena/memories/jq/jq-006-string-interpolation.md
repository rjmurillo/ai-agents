# Jq: String Interpolation

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

## Related

- [jq-001-basic-field-extraction](jq-001-basic-field-extraction.md)
- [jq-002-raw-output-mode](jq-002-raw-output-mode.md)
- [jq-003-object-construction](jq-003-object-construction.md)
- [jq-004-filtering-with-select](jq-004-filtering-with-select.md)
- [jq-005-array-operations](jq-005-array-operations.md)
