# jq: String Interpolation & Formatting

## Skill-JQ-006

**Statement**: Use `\(.field)` inside strings for template-style output.

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

# CSV output
gh issue list --json number,title,state \
  --jq -r '["number","title","state"], (.[] | [.number, .title, .state]) | @csv'

# TSV output
gh pr list --json number,title \
  --jq -r '.[] | [.number, .title] | @tsv'
```
