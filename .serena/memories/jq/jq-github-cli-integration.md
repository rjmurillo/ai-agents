# jq: GitHub CLI Integration Patterns

## Skill-JQ-009

**Statement**: Combine `--json` with `--jq` for efficient data extraction directly in gh commands.

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
```

## Skill-JQ-010: Handling Pagination

**Statement**: Use `--slurp` with `--paginate` to combine paginated results into a single array.

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

## Related

- [jq-aggregation](jq-aggregation.md)
- [jq-array-operations](jq-array-operations.md)
- [jq-conditionals](jq-conditionals.md)
- [jq-field-extraction](jq-field-extraction.md)
- [jq-filtering](jq-filtering.md)
