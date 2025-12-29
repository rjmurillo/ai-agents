# PR Maintenance Script Rollback Procedure

**Target**: `scripts/Invoke-PRMaintenance.ps1` and `.github/workflows/pr-maintenance.yml`

## Overview

This document describes rollback procedures for the PR maintenance automation script in case of issues during or after deployment.

## Quick Reference

| Scenario | Action | Time to Recover |
|----------|--------|-----------------|
| Script causing API exhaustion | Disable workflow | <1 min |
| Script causing incorrect reactions | Disable workflow, manual cleanup | <5 min |
| Script creating bad commits | Disable workflow, revert commits | <10 min |
| Concurrency lock stuck | Remove lock file | <30 sec |

## Rollback Procedures

### Level 1: Disable Workflow (Immediate)

**When to use**: Any issue requiring immediate stop of automation.

**Steps**:

1. Navigate to repository Actions tab
2. Click on "PR Maintenance" workflow
3. Click "..." menu → "Disable workflow"

**CLI Alternative**:

```bash
gh workflow disable "PR Maintenance"
```

**Time to recover**: <1 minute

### Level 2: Remove Stale Lock File

**When to use**: Script appears stuck or won't run despite no active instance.

**Location**: `.agents/logs/pr-maintenance.lock`

**Steps**:

```bash
# Check lock status
ls -la .agents/logs/pr-maintenance.lock

# Remove if stale (>15 min old)
rm .agents/logs/pr-maintenance.lock
```

**Time to recover**: <30 seconds

### Level 3: Revert GitHub Actions Workflow

**When to use**: Workflow configuration issue causing problems.

**Steps**:

```bash
# Disable workflow first
gh workflow disable "PR Maintenance"

# Revert workflow file to previous version
git log --oneline .github/workflows/pr-maintenance.yml
git checkout <previous-commit-sha> -- .github/workflows/pr-maintenance.yml
git commit -m "revert: disable pr-maintenance workflow due to issue"
git push
```

**Time to recover**: <5 minutes

### Level 4: Revert Script Changes

**When to use**: Script logic causing incorrect behavior.

**Steps**:

```bash
# Identify the commit before problematic changes
git log --oneline scripts/Invoke-PRMaintenance.ps1

# Revert specific commits
git revert <problematic-commit-sha>
git push
```

**Time to recover**: <10 minutes

### Level 5: Full Feature Rollback

**When to use**: Complete removal of PR maintenance automation needed.

**Steps**:

```bash
# Disable workflow
gh workflow disable "PR Maintenance"

# Delete workflow file
git rm .github/workflows/pr-maintenance.yml

# Optionally: remove script
git rm scripts/Invoke-PRMaintenance.ps1

# Commit
git commit -m "revert: remove PR maintenance automation"
git push
```

**Time to recover**: <15 minutes

## Recovery from Specific Issues

### Issue: Eyes Reactions on Wrong Comments

**Symptoms**: Bot added reactions to human comments or wrong PRs.

**Recovery**:

1. Disable workflow (Level 1)
2. Identify affected comments via log file:
   ```bash
   cat .agents/logs/pr-maintenance.log | grep "Acknowledging comment"
   ```
3. Remove reactions via API:
   ```bash
   gh api repos/{owner}/{repo}/issues/comments/{id}/reactions \
     -H "Accept: application/vnd.github+json" \
     --method GET | jq '.[] | select(.content == "eyes") | .id'

   gh api repos/{owner}/{repo}/issues/comments/{id}/reactions/{reaction_id} \
     -X DELETE
   ```

### Issue: Bad Merge Commits

**Symptoms**: Script pushed incorrect conflict resolution.

**Recovery**:

1. Disable workflow (Level 1)
2. Identify affected PRs from log:
   ```bash
   cat .agents/logs/pr-maintenance.log | grep "Successfully resolved"
   ```
3. For each affected PR:
   ```bash
   git checkout <pr-branch>
   git reset --hard HEAD~1  # Remove bad commit
   git push --force-with-lease
   ```

### Issue: PR Closed Incorrectly

**Symptoms**: Script closed a PR that shouldn't have been closed.

**Recovery**:

1. Disable workflow (Level 1)
2. Reopen the PR:
   ```bash
   gh pr reopen <pr-number>
   ```
3. Add comment explaining the issue:
   ```bash
   gh pr comment <pr-number> --body "This PR was incorrectly closed by automation. Reopened."
   ```

### Issue: API Rate Limit Exhausted

**Symptoms**: gh CLI commands failing with rate limit errors.

**Recovery**:

1. Check rate limit status:
   ```bash
   gh api rate_limit
   ```
2. Wait for reset (typically 1 hour from first request)
3. Increase threshold in script if persistent:
   ```powershell
   # In Test-RateLimitSafe function
   [int]$MinimumRemaining = 400  # Increase from 200
   ```

## Monitoring

### Log Files

Primary log location: `.agents/logs/pr-maintenance.log`

Key entries to monitor:

- `[ERROR]` - Any errors during execution
- `[WARN] PR #X has CHANGES_REQUESTED` - Blocked PRs
- `[ACTION]` - Actions taken (reactions, merges, closes)

### GitHub Actions

View workflow runs: Repository → Actions → "PR Maintenance"

Check for:

- Run duration (target: <2 min)
- Exit codes (0=success, 1=blocked PRs, 2=errors)
- Concurrency queuing (should not exceed 2 pending)

### Alerts

If workflow creates issues on failure, monitor the Issues tab for:

- Title pattern: "PR Maintenance Failed"
- Label: `automation-failure`

## Validation After Rollback

After any rollback:

1. Verify workflow is disabled:
   ```bash
   gh workflow list | grep "PR Maintenance"
   ```

2. Verify no active locks:
   ```bash
   ls -la .agents/logs/pr-maintenance.lock
   ```

3. Check recent PR activity for unintended changes:
   ```bash
   gh pr list --state all --limit 10
   ```

4. Run manual dry-run to validate fixes:
   ```bash
   pwsh scripts/Invoke-PRMaintenance.ps1 -DryRun -MaxPRs 5
   ```

## Escalation

If rollback procedures don't resolve the issue:

1. Open an issue with label `automation-failure`
2. Include:
   - Symptoms observed
   - Rollback steps attempted
   - Log files (`.agents/logs/pr-maintenance.log`)
   - GitHub Actions run URL

## Contacts

- **Repository Owner**: @rjmurillo
- **Automation Owner**: AI Agent System

## References

- **ADR**: [ADR-026: PR Automation Concurrency and Safety Controls](../architecture/ADR-026-pr-automation-concurrency-and-safety.md)
- **Security Review**: [SR-002: PR Automation Security Review](../security/SR-002-pr-automation-security-review.md)
- **Implementation Plan**: [PR Automation Implementation Plan](../planning/pr-automation-implementation-plan.md)
