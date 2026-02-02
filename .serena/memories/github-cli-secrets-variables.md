# GitHub CLI Secrets and Variables

## Skill-GH-Secret-001: Secret Management (95%)

**Statement**: Use `gh secret set` with `-f` for batch import; `--visibility` for org-level access.

```bash
# Set from value
gh secret set API_KEY --body "secret-value"

# Set from file
gh secret set SSH_KEY < ~/.ssh/id_rsa

# Batch import from .env file
gh secret set -f .env.production

# Environment-specific secret
gh secret set DB_PASSWORD --env production

# Org secret with visibility
gh secret set ORG_SECRET --org myorg --visibility all
gh secret set SHARED_SECRET --org myorg --repos repo1,repo2

# Dependabot secret
gh secret set NUGET_TOKEN --app dependabot

# List and delete
gh secret list
gh secret delete MY_SECRET
```

**Security Note**: Values are locally encrypted before transmission.

## Skill-GH-Variable-001: Variable Management (93%)

**Statement**: Use `gh variable` for non-sensitive config; supports repo/env/org scopes.

```bash
# Set variable
gh variable set MY_VAR --body "value"

# Get value
gh variable get MY_VAR

# Environment-specific
gh variable set DEBUG --env staging --body "true"

# Organization variable
gh variable set ORG_SETTING --org myorg --repos repo1,repo2
```

**Anti-pattern**: Using `gh variable` for sensitive data exposes values in logs. Always use `gh secret` for credentials.

## Related

- [github-cli-001-bidirectional-issue-linking](github-cli-001-bidirectional-issue-linking.md)
- [github-cli-anti-patterns](github-cli-anti-patterns.md)
- [github-cli-api-patterns](github-cli-api-patterns.md)
- [github-cli-extensions](github-cli-extensions.md)
- [github-cli-issue-operations](github-cli-issue-operations.md)
