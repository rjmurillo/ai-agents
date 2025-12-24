# GitHub CLI Workflow Runs

## Skill-GH-Run-001: Workflow Run Management (94%)

**Statement**: Use `gh run list` with `-w` for specific workflow; `gh run view --log-failed` for debugging.

```bash
# List runs for specific workflow
gh run list -w "CI"
gh run list -w ci.yml

# Filter by status
gh run list --status failure

# View only failed logs (FASTEST debugging)
gh run view 12345678 --log-failed

# Watch running workflow
gh run watch 12345678

# Exit with error if run failed
gh run view 12345678 --exit-status && echo "Passed"

# Download artifacts
gh run download 12345678 -n artifact-name
```

**Best Practice**: Always use `--log-failed` first when debugging. Shows only failed job logs, dramatically speeding diagnosis.

**Evidence**: Session 56 - Used `gh run view --log-failed` to immediately identify Import-Module path error.

## Skill-GH-Run-002: Workflow Triggering (92%)

**Statement**: Use `gh workflow run` for manual triggers; workflow must have `workflow_dispatch` trigger.

```bash
# Trigger with inputs
gh workflow run deploy.yml -f environment=staging -f version=1.2.3

# Trigger from specific branch
gh workflow run ci.yml --ref feature-branch

# View workflow definition
gh workflow view deploy.yml --yaml

# Enable/disable workflow
gh workflow enable deploy.yml
gh workflow disable deprecated.yml
```

**Prerequisite**: Workflow must include `on: workflow_dispatch:` trigger.
