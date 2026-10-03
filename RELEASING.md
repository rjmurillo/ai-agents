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
When OIDC is active, the Actions runtime exchanges a short-lived token with
npm. This replaces the need for a long-lived `NPM_TOKEN` secret for
authentication. The `publish.yml` workflow already requests `id-token: write`
on the publish job.

The workflow still references `NPM_TOKEN` as a fallback. If OIDC is active,
the token is ignored. If OIDC is unavailable (self-hosted runners, forks),
set `NPM_TOKEN` in the `npm` environment for token-based auth.

## Publishing a release

### First publish

```bash
cd packages/ai-agents-cli
npm publish --provenance --access public
```

The `--access public` flag is required on first publish for scoped packages.
Subsequent publishes inherit the access level.

### Standard release (from CI)

Publishing goes through the ADR-113 promotion gate. A real publish runs the gate
in enforcing mode, so it publishes only when the gate promotes, and until every
open finding is fixed it will block.

1. Update the version in `packages/ai-agents-cli/package.json` and merge it to the default branch.
2. Optional: create the release `vX.Y.Z` on that commit, so the gate can attach its manifest to it.
3. Go to [Actions > npm Publish > Run workflow](https://github.com/rjmurillo/ai-agents/actions/workflows/publish.yml)
   on the default branch. Set `dry-run: false` and optionally the `release-tag`.

The workflow builds the tarball once, hashes it, runs the gate against that digest,
and publishes the same file after checking the digest again.

The candidate is the head commit of the default branch, the commit the run starts
from, because npm provenance attests the run commit and no job checks out a ref an
input chose.

The `v*` tag trigger is dormant. A tag push runs the tagged commit's own copy of
the workflow, so the first job refuses it with the reason. Each tag push therefore
shows one red "Resolve Publish Route" run, and that is expected until the owner
creates the `v*` tag ruleset (issue #5636). Pushing a tag does not publish.

### Manual dry-run

Go to [Actions > npm Publish > Run workflow](https://github.com/rjmurillo/ai-agents/actions/workflows/publish.yml)
and select `dry-run: true` (the default). This builds and validates the package, runs
the gate advisory, and runs `npm publish --dry-run` without publishing.

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
git push origin main
# Merge the bump, then run the npm Publish workflow with dry-run false
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
| OIDC provenance error | `id-token: write` missing | `publish.yml` contains `id-token: write` on publish job |
| Tag/version mismatch | `release-tag` does not match the `package.json` version | Use the tag `vX.Y.Z` for the version on the candidate commit |
| Publish blocked | The promotion gate found open findings | Read the gate job's manifest artifact, fix or accept the findings |
| Tag push does nothing | The `v*` tag route is dormant until the tag ruleset exists | Run the workflow by dispatch from the default branch |
| Pack size warning | Bundle exceeds 50MB | Review `files` allowlist in `package.json`, exclude unnecessary assets |
