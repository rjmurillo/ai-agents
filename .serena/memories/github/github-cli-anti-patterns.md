# GitHub CLI Anti-Patterns and Security

## Anti-Pattern-GH-001: Repository Rename Silent Failures

**Problem**: After repo rename, `gh` commands fail silently in scripts.

**Solution**: Update local git remote URL after renames:

```bash
git remote set-url origin git@github.com:owner/new-repo-name.git
```

## Anti-Pattern-GH-002: Using GITHUB_TOKEN for workflow_run

**Problem**: `gh workflow run` with `GITHUB_TOKEN` causes panic errors.

**Solution**: Use PAT with `workflow` scope:

```yaml
env:
  GH_TOKEN: ${{ secrets.PAT_WITH_WORKFLOW_SCOPE }}
```

## Anti-Pattern-GH-003: Commands Outside Repositories

**Problem**: Many commands fail outside git repositories.

**Solution**: Use `-R owner/repo` flag:

```bash
gh pr list -R cli/cli
```

## Anti-Pattern-GH-004: Expecting Pagination by Default

**Problem**: List commands only return 30 items.

**Solution**: Use `--limit` or `--paginate`:

```bash
gh pr list -L 100
gh api --paginate repos/{owner}/{repo}/issues
```

## Anti-Pattern-GH-005: gh pr view for Review Threads

**Problem**: `gh pr view --json reviewThreads` fails with "Unknown JSON field".

**Solution**: Use GraphQL API for review threads:

```bash
gh api graphql -f query='query { repository(owner: $owner, name: $repo) { pullRequest(number: $number) { reviewThreads(first: 100) { nodes { id isResolved } } } } }'
```

## Anti-Pattern-GH-006: Direct Token Storage

**Problem**: Storing PATs in plain text.

**Solution**: Use `gh auth` credential store or CI secrets.

## Rate Limiting

| Auth Type | Limit |
|-----------|-------|
| Unauthenticated | 60/hour |
| PAT/OAuth | 5,000/hour |
| GITHUB_TOKEN (Actions) | 1,000/hour/repo |

```bash
# Check remaining
gh api rate_limit --jq '.resources.core'
```

## Skill-GH-Attestation-001: Artifact Verification (93%)

**Statement**: Use `gh attestation verify` for secure deployments.

```bash
# Verify artifact
gh attestation verify artifact.bin --repo owner/repo

# Verify OCI container
gh attestation verify oci://ghcr.io/owner/image:tag --owner owner

# With workflow enforcement
gh attestation verify artifact.bin --owner org --signer-workflow .github/workflows/build.yml
```

**Security Note**: Only signature.certificate and verifiedTimestamps are tamper-resistant.

## CI/CD Integration

```yaml
jobs:
  example:
    runs-on: ubuntu-latest
    env:
      GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    steps:
      - name: Create PR comment
        run: gh pr comment ${{ github.event.pull_request.number }} --body "CI passed!"
```

**Safe Variable Handling**:

```yaml
# GOOD: Use env vars for user content
env:
  PR_BODY: ${{ github.event.pull_request.body }}
run: gh pr comment $PR_NUMBER --body "$PR_BODY"

# BAD: Direct interpolation (injection risk)
run: gh pr comment --body "${{ github.event.pull_request.body }}"
```

## Related

- [github-cli-001-bidirectional-issue-linking](github-cli-001-bidirectional-issue-linking.md)
- [github-cli-api-patterns](github-cli-api-patterns.md)
- [github-cli-extensions](github-cli-extensions.md)
- [github-cli-issue-operations](github-cli-issue-operations.md)
- [github-cli-labels-cache](github-cli-labels-cache.md)
