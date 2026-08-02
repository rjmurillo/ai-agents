# jq: String Interpolation & Formatting

## Skill-JQ-006

**Statement**: Use `\(.field)` inside strings for template-style output.

```bash
# Basic interpolation
gh pr list --json number,title \
  --jq '.[] | "#\(.number): \(.title)"'
# Output: #123: Fix bug

# Multi-field formatting
gh issue list --json number,title,state \
  --jq '.[] | "[\(.state)] #\(.number) - \(.title)"'

# With conditionals
gh pr list --json number,isDraft \
  --jq '.[] | "#\(.number) \(if .isDraft then "(DRAFT)" else "" end)"'

# Building URLs
gh pr list --json number \
  --jq '.[] | "https://github.com/owner/repo/pull/\(.number)"'

# Tab-separated for shell parsing
gh issue list --json number,title,state \
  --jq '.[] | "\(.number)\t\(.title)\t\(.state)"'

# CSV output
gh issue list --json number,title,state \
  --jq '["number","title","state"], (.[] | [.number, .title, .state]) | @csv'

# TSV output
gh pr list --json number,title \
  --jq '.[] | [.number, .title] | @tsv'
```

## Related

- [jq-aggregation](jq-aggregation.md)
- [jq-array-operations](jq-array-operations.md)
- [jq-conditionals](jq-conditionals.md)
- [jq-field-extraction](jq-field-extraction.md)
- [jq-filtering](jq-filtering.md)
