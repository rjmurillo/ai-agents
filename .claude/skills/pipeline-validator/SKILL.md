---
name: pipeline-validator
version: 1.0.0
model: claude-sonnet-4-5
description: Validate CI/CD pipelines after PR creation. Discovers pipelines, triggers runs, monitors status, diagnoses failures, applies auto-fixes, and retries. Use after any change-making skill creates a PR that needs pipeline validation.
license: MIT
---

# Pipeline Validator

Post-PR pipeline validation workflow. Discovers pipelines, triggers runs, monitors completion, diagnoses failures, applies fixes, and retries until all pipelines pass.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `validate pipelines` | Full 8-step workflow |
| `discover pipelines` | Step 1: Find pipeline definitions |
| `trigger pipeline runs` | Step 3: Queue pipeline runs |
| `monitor pipeline status` | Step 4: Poll for completion |
| `diagnose pipeline failure` | Step 5: Analyze failure logs |

## When to Use

Use this skill when:

- A PR has been created and needs pipeline validation before merge
- Pipeline runs have failed and need diagnosis
- Auto-fix and retry cycles are needed for transient or known failures
- Any change-making skill (e.g., `windows-image-updater`) needs post-PR validation

## Process

### Step 1: Discover Pipelines

1. Scan the repository for pipeline definition files:
   - `.azure-pipelines/*.yml`
   - `.pipelines/*.yml`
   - `build/**/*.yml`
   - Root-level `azure-pipelines.yml`
2. Classify each pipeline by type: PR Build, Buddy Build, Buddy Release, Other
3. Record pipeline names and file paths

### Step 2: Identify Target Pipelines

1. Filter to pipelines triggered by PR events or manual dispatch
2. Exclude pipelines that are disabled or have path filters excluding the changed files
3. Produce a target list with pipeline name, type, and definition path

### Step 3: Trigger Pipeline Runs

1. For each target pipeline, trigger a run against the PR branch
2. Use Azure DevOps REST API or `az pipelines run` CLI
3. Record the run ID and URL for each triggered pipeline
4. Update the PR description with pipeline run links

### Step 4: Monitor Pipeline Status

1. Poll each pipeline run at 60-second intervals
2. Track status transitions: Queued, Running, Completed
3. Set a timeout of 120 minutes per pipeline run
4. Report intermediate status updates as PR comments (at 5-minute intervals)

### Step 5: Diagnose Failures

For each failed pipeline run:

1. Download the run logs
2. Match log content against known error patterns (see [error-patterns.md](references/error-patterns.md))
3. Classify the failure:
   - **Auto-fixable**: Known pattern with a documented fix
   - **Transient**: Infrastructure flake, retry without changes
   - **Investigation required**: Unknown pattern, escalate to human

### Step 6: Apply Auto-Fixes

For auto-fixable failures:

1. Apply the documented fix from the error pattern catalog
2. Commit the fix to the PR branch with a descriptive message
3. Push the commit

### Step 7: Retry

1. Re-trigger failed pipelines after fixes are applied
2. Track retry count per pipeline (maximum 3 retries)
3. If a pipeline fails after 3 retries, mark it as requiring investigation

### Step 8: Report Results

Update the PR description with a summary table:

```markdown
## Pipeline Validation Results

| Pipeline | Type | Status | Retries | Run Link |
|----------|------|--------|---------|----------|
| PR Build | PR | Passed | 0 | [Run #123](url) |
| Buddy Build | CI | Passed | 1 | [Run #124](url) |
| Buddy Release | CD | Passed | 0 | [Run #125](url) |
```

## Constraints

- Maximum 3 retry attempts per pipeline
- 120-minute timeout per pipeline run
- Do not auto-fix failures that modify production configuration
- Always update the PR description with run links before monitoring
- Log all diagnosis results, even for passing pipelines

## Composability

This skill is designed to be invoked by any skill that creates a PR needing pipeline validation. The calling skill creates the PR. This skill validates it.

Example integration:

1. `windows-image-updater` creates a PR with image updates
2. `pipeline-validator` is invoked with the PR number
3. `pipeline-validator` discovers, triggers, monitors, and reports

Any future migration skill (e.g., .NET version upgrades) can follow the same pattern.

## See Also

| Document | Content |
|----------|---------|
| [error-patterns.md](references/error-patterns.md) | 12-category error diagnosis catalog |
| `windows-image-updater` skill | Pre-PR change-making skill |
