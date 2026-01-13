# GitHub CLI API Patterns

## Skill-GH-API-001: Direct API Access (96%)

**Statement**: Use `gh api` for endpoints not covered by built-in commands; `--paginate` for complete results.

```bash
# POST request with data
gh api repos/{owner}/{repo}/issues -f title="Bug" -f body="Description"

# Pagination (all results)
gh api --paginate repos/{owner}/{repo}/issues

# JSON filtering with jq
gh api repos/{owner}/{repo}/issues --jq '.[].title'

# Slurp paginated results
gh api --paginate --slurp repos/{owner}/{repo}/issues --jq 'flatten | length'

# Cache responses
gh api --cache 1h repos/{owner}/{repo}/contributors

# GraphQL queries
gh api graphql -f query='query { viewer { login } }'
```

## Skill-GH-GraphQL-001: Single-Line Mutation Format (97%)

**Statement**: Use single-line query format (no newlines) for GraphQL mutations to avoid parsing errors.

```bash
# CORRECT - Single-line format
gh api graphql -f query='mutation($id: ID!, $body: String!) { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $id, body: $body}) { comment { id } } }' -f id="PRRT_xxx" -f body="Reply"

# WRONG - Multi-line format causes parsing errors
gh api graphql -f query='
mutation($id: ID!, $body: String!) {
  addPullRequestReviewThreadReply(...) { ... }
}'
```

**Evidence**: PR #212 - 20 threads resolved using single-line format.

## Skill-GH-Auth-001: Authentication Management (91%)

**Statement**: Use `gh auth refresh` to add scopes without re-login.

```bash
# Add scopes
gh auth refresh -s workflow
gh auth refresh -s project
gh auth refresh -s read:packages

# Check auth status
gh auth status

# View token
gh auth token
```

**Required Scopes**: Minimum: `repo`, `read:org`. Add `workflow` for Actions, `project` for Projects.

## Skill-GH-JSON-001: JSON Output Patterns (94%)

**Statement**: Use `--json` with field names, pipe to `jq` for transformations.

```bash
# With jq filtering
gh pr list --json number,title --jq '.[].title'

# Complex transformation
gh pr list --json number,title,labels \
  --jq '.[] | select(.labels | any(.name == "bug")) | .number'

# Raw output (no quotes)
gh pr view 123 --json title --jq -r '.title'
```

## Related

- [github-cli-001-bidirectional-issue-linking](github-cli-001-bidirectional-issue-linking.md)
- [github-cli-anti-patterns](github-cli-anti-patterns.md)
- [github-cli-extensions](github-cli-extensions.md)
- [github-cli-issue-operations](github-cli-issue-operations.md)
- [github-cli-labels-cache](github-cli-labels-cache.md)
