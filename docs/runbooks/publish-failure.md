# npm publish or promotion gate failure

This runbook covers the `@rjmurillo/ai-agents` npm package. The plugins do not
publish through npm; see [Bad plugin or package release](bad-release-rollback.md)
for those.

## Symptom

- The [npm Publish](../../.github/workflows/publish.yml) run fails in one of its
  jobs: "Resolve Publish Route", "Validate Package", "Promotion Gate",
  "Publish to npm", or "Attach manifest to release".
- The "Promotion Gate" job fails with a `block` verdict.
- A `v*` tag push shows one red "Resolve Publish Route" run.

## Confirm

1. Open the failed run from
   [Actions > npm Publish](https://github.com/rjmurillo/ai-agents/actions/workflows/publish.yml)
   and note which job failed.
2. A red "Resolve Publish Route" run from a tag push is expected. The tag route
   is dormant until the `v*` tag ruleset exists (issue #5636). A tag push does
   not publish. Run the workflow by dispatch from the default branch instead.
3. For a gate block, download the `promotion-manifest` artifact from the
   "Promotion Gate" job. It lists every finding with its class: remediated,
   accepted, expired, or unresolved. An unresolved or expired finding blocks an
   enforcing run.
4. Check the published state after any run. `npm view <package> version`
   reports only the `latest` dist-tag, so check the candidate version
   directly and list what the registry holds:

   ```bash
   npm view @rjmurillo/ai-agents@X.Y.Z version
   npm view @rjmurillo/ai-agents versions
   ```

   The first command answers for one exact version. The second lists every
   published version. If the package has never been published, both fail with
   E404 and exit 1, which is itself the answer: nothing reached the registry.
   Verified on 2026-11-03: the package returns E404 today.

## Recover

Match the failure to the troubleshooting table in
[RELEASING.md](../../RELEASING.md#troubleshooting). The common cases:

| Failed job or message | Fix |
|---|---|
| `ENEEDAUTH` or `E403 Forbidden` | Check OIDC, the `npm` environment, 2FA, and the scope link, as RELEASING.md describes |
| Tag and version mismatch | Set `release-tag` to `vX.Y.Z` for the version in `packages/ai-agents-cli/package.json` |
| Promotion gate `block` | Fix each unresolved or expired finding in the manifest on a branch, merge it, then dispatch the workflow again |
| "Attach manifest to release" fails | The publish already succeeded. Check npm with step 4 above and do not publish again. Attach the manifest to the release by hand |
| "Promotion Gate" fails at "Fetch the previous promoted manifest" | No `promotion-manifest` artifact exists. Read that step's log; it fails when GitHub cannot answer or the newest release asset is not a promoted manifest |
| Pack size warning | Review the `files` allowlist in `packages/ai-agents-cli/package.json` |

Do not add an entry to `.agents/governance/promotion-exceptions.json` to get past
a block. The repository has one code owner, so the gate accepts no exception
(ADR-113 decision 7). `scripts/validation/promotion_gate.py` reads every
exception record as unapproved.

Before a real publish, run the workflow once with `dry-run: true`. That builds
the package, runs the gate in advisory mode, and runs `npm publish --dry-run`.
An advisory block prints `WOULD BLOCK` and still exits 0, so read the manifest.

If a bad version already reached npm, follow
[Bad plugin or package release](bad-release-rollback.md).

## Escalate

`publish.yml`, `promotion-gate.yml`, `scripts/validation/promotion_gate.py`, and
the promotion governance files belong to `@rjmurillo` (`.github/CODEOWNERS`).
Only the owner can change the `npm` environment, npm account settings, or the
tag ruleset.

## Links

- [RELEASING.md](../../RELEASING.md)
- [Promotion Gate workflow](../../.github/workflows/promotion-gate.yml)
