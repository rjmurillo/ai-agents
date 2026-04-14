# Releasing @rjmurillo/ai-agents

## One-time setup

### 1. Link npm scope to GitHub repo (required for provenance)

Go to [npmjs.com/settings/rjmurillo/packages](https://www.npmjs.com/settings/rjmurillo/packages),
find `@rjmurillo/ai-agents`, and link it to the `rjmurillo/ai-agents` GitHub repository.
This must happen before the first publish with `--provenance`.

### 2. Enable 2FA on npm account

npm requires 2FA for publishing scoped packages with provenance.
Enable it at [npmjs.com/settings/~/tfa](https://www.npmjs.com/settings/~/tfa).

### 3. Configure GitHub environment

Create a GitHub environment named `npm` at
`Settings > Environments > New environment`. No secrets are required
when using OIDC. If OIDC is not available, add `NPM_TOKEN` as an
environment secret (automation token from npm).

### 4. Verify OIDC

OIDC provenance uses GitHub Actions' built-in `id-token: write` permission.
No npm token is needed when publishing from CI with `--provenance`.
The `publish.yml` workflow already requests this permission on the publish job.

If OIDC is not configured, set `NPM_TOKEN` in the `npm` environment and
the workflow falls back to token-based auth.

## Publishing a release

### First publish

```bash
cd packages/ai-agents-cli
npm publish --provenance --access public
```

The `--access public` flag is required on first publish for scoped packages.
Subsequent publishes inherit the access level.

### Standard release (from CI)

1. Update the version in `packages/ai-agents-cli/package.json`.
2. Commit: `git commit -m "chore(cli): bump version to X.Y.Z"`.
3. Tag: `git tag vX.Y.Z`.
4. Push: `git push origin main --tags`.

The `publish.yml` workflow triggers on `v*` tags and publishes automatically.

### Manual dry-run

Go to [Actions > npm Publish > Run workflow](../../actions/workflows/publish.yml)
and select `dry-run: true`. This validates the package without publishing.

## Rollback procedures

### Deprecate a version

Marks a version as deprecated. Users see a warning on install but can still use it.

```bash
npm deprecate @rjmurillo/ai-agents@X.Y.Z "reason for deprecation"
```

### Publish a patch to supersede a bad version

```bash
cd packages/ai-agents-cli
# Fix the issue, bump patch version
npm version patch
git push origin main --tags
# CI publishes the new version automatically
```

### Remove from search (yank)

npm does not support true un-publish after 72 hours. To remove a version
from search results without breaking existing installs:

```bash
npm deprecate @rjmurillo/ai-agents@X.Y.Z "yanked: use X.Y.Z+1 instead"
```

For versions published less than 72 hours ago:

```bash
npm unpublish @rjmurillo/ai-agents@X.Y.Z
```

Do not unpublish the entire package. Only unpublish specific versions, and
only within the 72-hour window.

## Verification

After any publish, verify:

```bash
# Check version on registry
npm view @rjmurillo/ai-agents version

# Check provenance badge
npm view @rjmurillo/ai-agents

# Test from clean environment
npx @rjmurillo/ai-agents --version
```

The package page on npmjs.com should show a green provenance badge
linking back to this repository's publish workflow.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ENEEDAUTH` | Missing npm token or OIDC not configured | Add `NPM_TOKEN` to `npm` environment, or verify OIDC setup |
| `E403 Forbidden` | 2FA not enabled or scope not linked | Enable 2FA, link scope to repo in npm UI |
| `ENOSPC` provenance error | `id-token: write` missing | Verify `publish.yml` has `id-token: write` on publish job |
| Tag/version mismatch | Tag `vX.Y.Z` does not match `package.json` version | Update `package.json` version before tagging |
| Pack size warning | Bundle exceeds 50MB | Review `files` allowlist in `package.json`, exclude unnecessary assets |
