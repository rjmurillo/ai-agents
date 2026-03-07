# Error Patterns: Pipeline Validator

12-category error diagnosis catalog for pipeline failure analysis.

## Category 1: NuGet Restore Failures

**Pattern**: `error NU1101`, `Unable to find package`, `version conflict`

**Cause**: Missing or incompatible NuGet packages after a version bump.

**Auto-fix**: Re-run dependency resolution from the windows-image-updater skill (Phase 2). Update the conflicting package version and commit.

**Severity**: Auto-fixable

## Category 2: Build Compilation Errors

**Pattern**: `error CS`, `error MSB`, `Build FAILED`

**Cause**: Code changes introduced a compilation error, or a dependency change broke API compatibility.

**Auto-fix**: None. Requires investigation of the specific compiler error.

**Severity**: Investigation required

## Category 3: Container Image Pull Failures

**Pattern**: `manifest unknown`, `image not found`, `pull access denied`

**Cause**: The specified container image does not exist in the registry, or the pipeline agent lacks pull permissions.

**Auto-fix**: Verify the image tag exists. If the tag is wrong, update the pipeline YAML and commit.

**Severity**: Auto-fixable (if tag mismatch), Investigation required (if permissions)

## Category 4: Test Failures

**Pattern**: `Failed!`, `Tests failed`, `Assert.`, `Expected .* but`

**Cause**: Unit or integration tests are failing due to behavioral changes from the update.

**Auto-fix**: None. Test failures require human review to determine if the test or the code is wrong.

**Severity**: Investigation required

## Category 5: Timeout Errors

**Pattern**: `TimeoutException`, `exceeded the maximum`, `timed out`

**Cause**: A pipeline step or test exceeded its time limit. Often transient due to infrastructure load.

**Auto-fix**: Retry the pipeline run. If timeout persists after 2 retries, escalate.

**Severity**: Transient

## Category 6: Agent Pool Unavailability

**Pattern**: `No agent found`, `pool .* has no agents`, `all agents are busy`

**Cause**: The build agent pool is exhausted or offline.

**Auto-fix**: Retry after a delay. Agent pools are shared resources that recover on their own.

**Severity**: Transient

## Category 7: ConfigGen Validation Errors

**Pattern**: `ConfigGen validation failed`, `schema mismatch`, `invalid pipeline definition`

**Cause**: ConfigGen generated YAML that does not pass the pipeline schema validator.

**Auto-fix**: Re-run ConfigGen with updated parameters. If the schema has changed, update the ConfigGen configuration.

**Severity**: Auto-fixable

## Category 8: Artifact Publishing Failures

**Pattern**: `Failed to publish artifact`, `artifact upload error`, `storage quota exceeded`

**Cause**: Pipeline artifact storage is full or the artifact path is invalid.

**Auto-fix**: None for quota issues. For path issues, fix the artifact path in the pipeline definition.

**Severity**: Investigation required

## Category 9: Authentication and Authorization

**Pattern**: `401 Unauthorized`, `403 Forbidden`, `access denied`, `token expired`

**Cause**: Service connection, PAT, or managed identity credentials are expired or lack permissions.

**Auto-fix**: None. Credential management requires human intervention.

**Severity**: Investigation required

## Category 10: Infrastructure Flakes

**Pattern**: `network unreachable`, `DNS resolution failed`, `connection reset`, `503 Service Unavailable`

**Cause**: Transient network or infrastructure issues in the build environment.

**Auto-fix**: Retry the pipeline run.

**Severity**: Transient

## Category 11: YAML Syntax Errors

**Pattern**: `Invalid YAML`, `mapping values are not allowed`, `unexpected end of stream`

**Cause**: Malformed YAML in pipeline definition files, often from merge conflicts or manual edits.

**Auto-fix**: None. Report syntax errors with line numbers for human review. Automated fixing of YAML syntax is high-risk and can alter logic unintentionally.

**Severity**: Investigation required

## Category 12: OneBranch-Specific Errors

**Pattern**: `ob_`, `OneBranch`, `CloudBuild`, `cdpx`

**Cause**: OneBranch platform-specific failures, such as missing build variables, unsupported configurations, or platform version mismatches.

**Auto-fix**: Check OneBranch documentation for the specific error code. Common fixes include updating the `ob_` variable definitions or the CloudBuild manifest.

**Severity**: Auto-fixable (for known patterns), Investigation required (for unknown)

## Diagnosis Workflow

When analyzing a failure log:

1. Extract the first error line (skip warnings)
2. Match against patterns above in order (most specific first)
3. If multiple categories match, use the earliest error in the log
4. Record the category, matched pattern, and log excerpt
5. Apply the prescribed action based on severity

## Severity Actions

| Severity | Action |
|----------|--------|
| Auto-fixable | Apply fix, commit, retry pipeline |
| Transient | Retry pipeline without changes (up to 3 times) |
| Investigation required | Add PR comment with diagnosis, assign to human reviewer |
