# Releasing @rjmurillo/ai-agents

## One-time setup

The workflow authenticates to npm in one of two ways. Trusted publishing (OIDC)
needs no stored secret. A granular access token in the `npm` environment is the
fallback. The first publish must use the token, because npm can only link a
trusted publisher to a package that already exists. npm/cli#8544 tracks that
limit.

### 1. Check the GitHub environment

The `publish.yml` publish job runs in the GitHub environment `npm` and requests
`id-token: write`. On 2026-11-18 the `npm` environment existed, and its
deployment branches allowed only `main`. No environment change is required.

Keep that branch rule. A dispatch from any other branch runs that branch's copy
of `publish.yml`, so the rule is what keeps `NPM_TOKEN` and the OIDC publish
claim away from it (ADR-101). If the environment is ever deleted, the next run
recreates it with no rule. Restore the rule at Settings > Environments > `npm`
> Deployment branches and tags.

Before every real publish, confirm the rule is still in place:

```bash
gh api repos/rjmurillo/ai-agents/environments/npm/deployment-branch-policies \
  --jq '[.branch_policies[].name]'
```

It must print `["main"]`. Any other output means stop and restore the rule.

### 2. Enable 2FA on the npm account

Enable it at [npmjs.com/settings/~/tfa](https://www.npmjs.com/settings/~/tfa).

### 3. First publish: bootstrap with a short-lived token

Do this right before the first real publish, when the promotion gate is ready
to promote. Do not publish from a laptop. npm generates provenance only from a
supported cloud CI runner, and a local publish skips the promotion gate.

1. On npmjs.com, open your profile picture > Access Tokens > Generate New Token.
   - Check Bypass two-factor authentication. CI cannot answer an OTP prompt.
   - Under Packages and scopes, set Permissions to Read and write (publish and
     stage). Choose Only select packages and scopes, then the `@rjmurillo` scope.
   - Set Expiration to a custom date one or two days out.
2. Add the token as the environment secret `NPM_TOKEN` in the `npm`
   environment. Paste it there and nowhere else.
3. Run the standard release below.
4. Delete the `NPM_TOKEN` secret, then revoke the token on npmjs.com. Do this
   even when the publish fails. Make a new token for the next attempt.

### 4. Every later publish: trusted publishing

Set this up right before the next release run. A new trusted publisher config
expires if it does not complete a publish within 2 days.

On npmjs.com, open Packages > `@rjmurillo/ai-agents` > Settings > Trusted
publishing, choose GitHub Actions, and enter:

| Field | Value |
|---|---|
| Organization or user | `rjmurillo` |
| Repository | `ai-agents` |
| Workflow filename | `publish.yml` |
| Environment name | `npm` |
| Allowed actions | `npm publish` (checked) |

Configs created after 2026-09-03 allow only `npm stage publish` by default.
The workflow runs `npm publish`, so check that action.

Trusted publishing needs npm 11.5.1 or later and Node 22.14.0 or later. The
publish job installs Node `lts/*`, which meets both. npm generates provenance on its own when it
publishes through OIDC from a public repository.

After one trusted publish succeeds, open the package's Settings > Publishing
access and choose Require two-factor authentication and disallow tokens.

The workflow still passes `NODE_AUTH_TOKEN` from `secrets.NPM_TOKEN`. npm tries
the OIDC exchange first and uses its token when the exchange succeeds. When the
exchange fails, npm falls back to `NODE_AUTH_TOKEN`, which is empty once the
secret is deleted.

## Publishing a release

### Standard release (from CI)

Publishing goes through the ADR-113 promotion gate. A real publish runs the gate
in enforcing mode, so it publishes only when the gate promotes, and until every
open finding is fixed it will block.

1. Update the version in `packages/ai-agents-cli/package.json` and `VERSION` in `packages/ai-agents-cli/src/cli.ts` to the same value, and merge both to the default branch.
2. Create the release `vX.Y.Z` on that commit. A real publish needs `release-tag`, and the final job attaches the gate manifest to that release, so the job fails after npm has published if the release does not exist.
3. Go to [Actions > npm Publish > Run workflow](https://github.com/rjmurillo/ai-agents/actions/workflows/publish.yml)
   on the default branch. Set `dry-run: false` and `release-tag` to `vX.Y.Z` for the
   `package.json` version. A real publish without `release-tag` is refused.

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
the gate advisory, and runs `npm publish --dry-run` without publishing. Run it from
`main`: the `npm` environment refuses a run from any other branch.

## Writing release notes

Release notes start from a generated draft and end as a hand-written narrative.

### 1. Generate the draft

`.github/release.yml` sorts merged PRs into categories by label: Security,
Features, Fixes, Dependencies, Documentation, CI and build, and Other changes.
A PR lands in the first category that matches one of its labels. Most labels
come from `.github/labeler.yml`, which keys on changed paths and branch prefixes
such as `feat/` and `fix/`.

To get the draft, open
[Draft a new release](https://github.com/rjmurillo/ai-agents/releases/new),
choose the tag and the previous tag, then click **Generate release notes**.
The draft fills the release body. Nothing publishes until you click
**Publish release**, so you can edit or discard the draft first.

### 2. Write the narrative

Follow [docs/release-notes-styleguide.md](docs/release-notes-styleguide.md).
Use the draft as raw input, not as the published body:

1. Group the Features and Fixes entries into benefit-focused feature sections.
2. Put the commit count and the closed-issue count in the opening paragraph,
   as the style guide asks. Get the commit count with
   `git rev-list --count vA.B.C..vX.Y.Z`. Get the issue count from a GitHub
   issue search, `is:issue is:closed closed:START..END`, using the dates of
   the two tags.
3. Move the full categorized list into the "All Changes" section.
4. Take the contributor list from the draft's "New Contributors" block and PR authors.

Unlabeled PRs fall into "Other changes". Before you publish, add the right
label to any PR that belongs in a named category, then regenerate the draft.

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
| `ENEEDAUTH` | No trusted publisher matched and no `NPM_TOKEN` | First publish: follow setup step 3. Later: check the trusted publisher fields in setup step 4 |
| `E403 Forbidden` | First publish: the token lacks write access, or 2FA blocks a token without bypass. Later: the trusted publisher does not allow `npm publish`, or the package disallows tokens and OIDC did not match | First publish: recreate the token per setup step 3. Later: check the trusted publisher fields and Allowed actions in setup step 4 |
| OIDC provenance error | `id-token: write` missing | `publish.yml` contains `id-token: write` on publish job |
| Tag/version mismatch | `release-tag` does not match the `package.json` version | Use the tag `vX.Y.Z` for the version on the candidate commit |
| `a real publish needs release-tag` | `dry-run` is `false` and `release-tag` is empty | Set `release-tag` to `vX.Y.Z` |
| `lacks package/bundle/assets/*` | The tarball holds no kit; the bundle build did not run | Check the `Build bundle` step ran before `Pack the tarball once` |
| Publish blocked | The promotion gate found open findings | Read the gate job's manifest artifact, fix or accept the findings |
| Tag push does nothing | The `v*` tag route is dormant until the tag ruleset exists | Run the workflow by dispatch from the default branch |
| Pack size warning | Bundle exceeds 50MB | Review `files` allowlist in `package.json`, exclude unnecessary assets |
