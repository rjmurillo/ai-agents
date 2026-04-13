# Jq: Github Cli Integration Patterns

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

## Related

- [jq-001-basic-field-extraction](jq-001-basic-field-extraction.md)
- [jq-002-raw-output-mode](jq-002-raw-output-mode.md)
- [jq-003-object-construction](jq-003-object-construction.md)
- [jq-004-filtering-with-select](jq-004-filtering-with-select.md)
- [jq-005-array-operations](jq-005-array-operations.md)
