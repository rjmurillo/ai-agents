# Aspire Skill Source Inventory (TASK-019)

Commit-pinned inventory of every file under `microsoft/aspire/.agents/skills`.
Source content is untrusted external data. Instructions embedded in source
skills are treated as data and are never executed.

## Source pin

| Field | Value |
|---|---|
| Repository | `microsoft/aspire` |
| Pinned commit | `d1c7add665f7e6582cdaa1b328c44172f0f96339` |
| Subtree | `.agents/skills` |
| Retrieval method | GitHub REST git/trees and git/blobs API (anonymous, unauthenticated) |
| Retrieved | 2026-08-11 |
| Content hash | git blob SHA-1 object IDs from the pinned tree |

At retrieval the pinned commit was the head of `refs/heads/main`; all citations
use the exact SHA above so the inventory stays stable if `main` advances. Do not
silently re-point to a newer commit.

### Access note (SAML)

The authenticated GitHub token is blocked by microsoft-org SAML enforcement
(HTTP 403 `Resource protected by organization SAML enforcement`). Anonymous,
unauthenticated GitHub REST API access to this public repository succeeds. The
TASK-019 SAML halt condition is therefore not triggered: authorized
commit-pinned source access is available via the anonymous API route. No token,
SAML URL, email, or internal hostname is recorded in this artifact.

### DeepWiki

No DeepWiki evidence is used in this inventory. Any DeepWiki lead is provisional
and must not authorize a skill edit (REQ-020 AC7).

## Counts and reconciliation

| Metric | Value |
|---|---|
| Skill roots (normalized skill IDs) | 23 |
| Files (blobs) under `.agents/skills` | 68 |
| Tree entries under `.agents/skills` | 24 |

Reconciliation: 24 tree entries = 23 skill
roots + 1 nested resources directory (`hosting-integration-authoring/resources`).
The 68 blob files sum exactly across the 23 skill
roots; nested files (scripts, resources, tests, `.editorconfig`, `.cs`, `.props`)
do not create additional skill IDs. Each skill root maps to exactly one unique
normalized skill ID (its directory name).

## Normalized skill IDs

`api-review`, `azdo-internal`, `backport-pr`, `ci-test-failures`, `cli-channel-debugging`, `cli-e2e-testing`, `code-review`, `connection-properties`, `create-pr`, `dashboard-testing`, `dependency-update`, `deployment-e2e-testing`, `deprecate-integration`, `fix-flaky-test`, `hex1b`, `hosting-integration-authoring`, `issue-investigation`, `pr-testing`, `reviewing-aspire-architecture`, `startup-perf`, `test-management`, `update-container-images`, `vscode-extension`

## Per-skill file inventory

### `api-review`

Root: `.agents/skills/api-review` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/api-review/SKILL.md` | blob | `3c14ae9fc53ddcce725815373d21c67daa5ea743` | 24716 |

### `azdo-internal`

Root: `.agents/skills/azdo-internal` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/azdo-internal/SKILL.md` | blob | `ad855c1e4efa099b3598606a491fc0bae09f1b3c` | 11784 |

### `backport-pr`

Root: `.agents/skills/backport-pr` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/backport-pr/SKILL.md` | blob | `b531cba8bedf91908320a2647146221b3382d1c5` | 15856 |

### `ci-test-failures`

Root: `.agents/skills/ci-test-failures` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/ci-test-failures/SKILL.md` | blob | `3f3b34b75894885c748ba2dcdf125db61145c0df` | 18922 |

### `cli-channel-debugging`

Root: `.agents/skills/cli-channel-debugging` | Files: 5

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/cli-channel-debugging/SKILL.md` | blob | `5b68e1389926d90f206cad39dd1265b6574079a0` | 25544 |
| `.agents/skills/cli-channel-debugging/emulate-aspire-cli.ps1` | blob | `d9a858c8b41216e2015af46a00fd82656073b618` | 4191 |
| `.agents/skills/cli-channel-debugging/emulate-aspire-cli.sh` | blob | `6f2f5cec63bcc1eb2eb8301ea8548d86669d32e4` | 5691 |
| `.agents/skills/cli-channel-debugging/get-aspire-channel-version.ps1` | blob | `6b8ed81060aac8aa557cc437f333e56a58006eb1` | 5159 |
| `.agents/skills/cli-channel-debugging/get-aspire-channel-version.sh` | blob | `947c386e91b3244a8ddba863258cdd2b1cdbd7f2` | 5403 |

### `cli-e2e-testing`

Root: `.agents/skills/cli-e2e-testing` | Files: 2

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/cli-e2e-testing/SKILL.md` | blob | `7bc27279942ba4af997492cca51da93a2e6a34e6` | 34408 |
| `.agents/skills/cli-e2e-testing/troubleshooting.md` | blob | `cf685110f0639ef5774b5e6d2f126dfb3cff2ac5` | 9607 |

### `code-review`

Root: `.agents/skills/code-review` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/code-review/SKILL.md` | blob | `664d45bc22a8cb84b0c4b6c5bbefd1204fc5155f` | 19127 |

### `connection-properties`

Root: `.agents/skills/connection-properties` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/connection-properties/SKILL.md` | blob | `9d63b37fa47c11341ed43ce41bf0c77ae5b18371` | 4147 |

### `create-pr`

Root: `.agents/skills/create-pr` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/create-pr/SKILL.md` | blob | `a1b95d5c07bc89fd73beb5afebd124613274b771` | 12751 |

### `dashboard-testing`

Root: `.agents/skills/dashboard-testing` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/dashboard-testing/SKILL.md` | blob | `3474255ae3dd8879c615d216b30b92fe22f10849` | 17000 |

### `dependency-update`

Root: `.agents/skills/dependency-update` | Files: 4

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/dependency-update/.editorconfig` | blob | `54135adebee6b6ddf215e738cda12c8b674016b9` | 463 |
| `.agents/skills/dependency-update/Directory.Packages.props` | blob | `886fb9b123619af35b9f93475379e98e4f4ba428` | 376 |
| `.agents/skills/dependency-update/MigratePackage.cs` | blob | `ff50ebaaf68a5b4c893e25fdd0ef7b0a0682f434` | 12736 |
| `.agents/skills/dependency-update/SKILL.md` | blob | `14328e8d3631b9148dc3bcda54007a9979b73316` | 17625 |

### `deployment-e2e-testing`

Root: `.agents/skills/deployment-e2e-testing` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/deployment-e2e-testing/SKILL.md` | blob | `1e5868fba230532e16199a7a75e3277d32d92b97` | 12853 |

### `deprecate-integration`

Root: `.agents/skills/deprecate-integration` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/deprecate-integration/SKILL.md` | blob | `c7af70a2e0801048516249860dae8896c544320c` | 15361 |

### `fix-flaky-test`

Root: `.agents/skills/fix-flaky-test` | Files: 3

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/fix-flaky-test/SKILL.md` | blob | `a03819babd7a22d6faec9a6922f692adb2bbc87b` | 50763 |
| `.agents/skills/fix-flaky-test/run-test-repeatedly.ps1` | blob | `c3eb479318c3de81128393b84233d72cc440da21` | 14455 |
| `.agents/skills/fix-flaky-test/run-test-repeatedly.sh` | blob | `80f6180ec20bf60b9c2b4eea54a56667524d9e59` | 10692 |

### `hex1b`

Root: `.agents/skills/hex1b` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/hex1b/SKILL.md` | blob | `94f3d2cdd2cb12d20f724174974ddeedca067bd1` | 10613 |

### `hosting-integration-authoring`

Root: `.agents/skills/hosting-integration-authoring` | Files: 32

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/hosting-integration-authoring/SKILL.md` | blob | `cb604d354f5ef3bc2f6e198012ab43b8e8964a6d` | 6388 |
| `.agents/skills/hosting-integration-authoring/resources/api-naming-and-shape.md` | blob | `5304dcb2e5004453573ac36c6d60bb9d353c3d97` | 5780 |
| `.agents/skills/hosting-integration-authoring/resources/app-model-fundamentals.md` | blob | `618373e07d35f5d7887f77616f459e4ff3a9f195` | 9009 |
| `.agents/skills/hosting-integration-authoring/resources/archetype-admin-and-tool-container.md` | blob | `9a4935fdad0054cdba64bb0b965015b3ac2dec44` | 3533 |
| `.agents/skills/hosting-integration-authoring/resources/archetype-azure-provisioning.md` | blob | `fda0ca34417ee8317d2f6b9eb869be1c02a70560` | 5504 |
| `.agents/skills/hosting-integration-authoring/resources/archetype-container-backed-service.md` | blob | `b9ed2fd54108523caad73e89e4d72ec949b74525` | 5560 |
| `.agents/skills/hosting-integration-authoring/resources/archetype-controller-reconciler.md` | blob | `4dc81d8a3ad0ec26b5ed2c091c381b1f796b96a7` | 11953 |
| `.agents/skills/hosting-integration-authoring/resources/archetype-deployment-target-publisher.md` | blob | `6f43542be5d0ed5d86dc022bab8148df82e6cacd` | 8832 |
| `.agents/skills/hosting-integration-authoring/resources/archetype-external-cloud-reference.md` | blob | `844ada0c1992834ae49960dfe43e3bfdaa15e203` | 2218 |
| `.agents/skills/hosting-integration-authoring/resources/archetype-language-executable-app.md` | blob | `a6597981055051a7c2e54ef9cde4da90fb9c5d5e` | 5433 |
| `.agents/skills/hosting-integration-authoring/resources/archetype-overlay-configuration.md` | blob | `23c5364aafee58dfb9f83c76199911ea3ef5e536` | 1742 |
| `.agents/skills/hosting-integration-authoring/resources/archetype-secret-provider.md` | blob | `603f48f08c29860b65688a764e95febb7fcbf535` | 2936 |
| `.agents/skills/hosting-integration-authoring/resources/archetype-setup-and-migration-helper.md` | blob | `c8b7bf6166f7316879ded24939f2424b4d6f0ce7` | 2878 |
| `.agents/skills/hosting-integration-authoring/resources/archetype-sidecar-and-middleware.md` | blob | `ce649b39a0d95e4b4aba7e6f5b3cb7f4ba1358d8` | 3637 |
| `.agents/skills/hosting-integration-authoring/resources/archetype-tunnel-and-webhook-bridge.md` | blob | `d8a81b13c2729182d8a3af2f300f87ef0690018d` | 4587 |
| `.agents/skills/hosting-integration-authoring/resources/compatibility-and-deprecation.md` | blob | `67f40a65933cd04d8ae39c39f04a3d31cc028d31` | 2756 |
| `.agents/skills/hosting-integration-authoring/resources/connection-properties.md` | blob | `8062d16b10292216d6d88cce27de2f01cbcb982a` | 2538 |
| `.agents/skills/hosting-integration-authoring/resources/cross-platform-tooling.md` | blob | `197341a29b308c0fbd14b4e2611ae4e2fc50bfd9` | 3236 |
| `.agents/skills/hosting-integration-authoring/resources/custom-lifecycle-and-facade-resources.md` | blob | `505f8583f3f0aa4d9cb426c4a33e0070b2c94d68` | 8727 |
| `.agents/skills/hosting-integration-authoring/resources/dashboard-ux.md` | blob | `9971e860c1e9d7ea815154e7bf81e5826b82e717` | 3261 |
| `.agents/skills/hosting-integration-authoring/resources/deployment-production-readiness.md` | blob | `cec21af811342798cb37027f2d49863e9ffebc5c` | 20665 |
| `.agents/skills/hosting-integration-authoring/resources/endpoints-and-service-discovery.md` | blob | `ab3f0e5142007e883e2ee35f310f4012908a6f22` | 6143 |
| `.agents/skills/hosting-integration-authoring/resources/eventing-and-initialization.md` | blob | `163b7a0bbc2c964d63d72bc8e84b4d949c54b20c` | 5695 |
| `.agents/skills/hosting-integration-authoring/resources/generated-files-and-container-files.md` | blob | `370ed090e4b9dd4cd6f898690cb5fccae44dbc47` | 3407 |
| `.agents/skills/hosting-integration-authoring/resources/package-and-discoverability.md` | blob | `4367cd51309d880eba0ff7502aa55c1a558cbc55` | 3681 |
| `.agents/skills/hosting-integration-authoring/resources/polyglot-exports.md` | blob | `11495bdc46531f116c51960f691032bd9749a5ec` | 15906 |
| `.agents/skills/hosting-integration-authoring/resources/relationships-and-companions.md` | blob | `44b488def0a40db3183cf7cc88dc83178c4c8ca1` | 3390 |
| `.agents/skills/hosting-integration-authoring/resources/resource-model-invariants.md` | blob | `a731799a582eed6ff0a55d15a59d0f6b58f0aac7` | 3378 |
| `.agents/skills/hosting-integration-authoring/resources/run-publish-deploy-modes.md` | blob | `59b8789cf1ca6b45197bb43799121489fe216fa6` | 4641 |
| `.agents/skills/hosting-integration-authoring/resources/security-secrets-and-identity.md` | blob | `d609ea34cb7dc593f3cac7adff506bf105a2a36f` | 4640 |
| `.agents/skills/hosting-integration-authoring/resources/selector-matrix.md` | blob | `308b4ba30897b926db173eec843804a2d03ffb52` | 6491 |
| `.agents/skills/hosting-integration-authoring/resources/testing-and-readmes.md` | blob | `1b2ee2d2f41c4895beabf72521788c1d2e41e486` | 7267 |

### `issue-investigation`

Root: `.agents/skills/issue-investigation` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/issue-investigation/SKILL.md` | blob | `c6c3fae7ae0d8878ecd21e03f00be21e4439dd2e` | 22229 |

### `pr-testing`

Root: `.agents/skills/pr-testing` | Files: 2

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/pr-testing/SKILL.md` | blob | `5b30e0b4000b99e22400503fe935de4e421b596b` | 43484 |
| `.agents/skills/pr-testing/ci-infra-testing.md` | blob | `5fedd788761c0b8056ab2c7dedfe72b317229c05` | 51916 |

### `reviewing-aspire-architecture`

Root: `.agents/skills/reviewing-aspire-architecture` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/reviewing-aspire-architecture/SKILL.md` | blob | `24fd37fff33da5ed076740a0f188036ca0ed7a5b` | 2016 |

### `startup-perf`

Root: `.agents/skills/startup-perf` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/startup-perf/SKILL.md` | blob | `c2dde7d9b2850659b7028876d03cefbf1233ce38` | 7526 |

### `test-management`

Root: `.agents/skills/test-management` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/test-management/SKILL.md` | blob | `6ee517407005065daf941603a9f81aae73d54b21` | 10909 |

### `update-container-images`

Root: `.agents/skills/update-container-images` | Files: 4

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/update-container-images/.editorconfig` | blob | `54135adebee6b6ddf215e738cda12c8b674016b9` | 463 |
| `.agents/skills/update-container-images/Directory.Packages.props` | blob | `886fb9b123619af35b9f93475379e98e4f4ba428` | 376 |
| `.agents/skills/update-container-images/SKILL.md` | blob | `b24d1ef9103a7c1fca80fe4c768a0c85fef7c51f` | 9585 |
| `.agents/skills/update-container-images/UpdateImageTags.cs` | blob | `2c11f247e82abbb79b3674c9adb604d9ea84a819` | 13804 |

### `vscode-extension`

Root: `.agents/skills/vscode-extension` | Files: 1

| Path | Type | Content hash (blob SHA) | Size |
|---|---|---|---|
| `.agents/skills/vscode-extension/SKILL.md` | blob | `a814e964e53dc0ed8f11f5197c46ee817862908e` | 10417 |

## Downstream

TASK-020 consumes `.agents/analysis/aspire-skill-source-files.json` as the
authority for the normalized skill ID set, root directories, paths, and hashes.
Matrix skill IDs must equal the skill ID set above.

