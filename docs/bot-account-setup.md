# Bot Account Setup and Maintenance

This guide explains how to configure bot accounts (like `rjmurillo-bot`) to work properly with GitHub Actions workflows in this repository.

## Table of Contents

- [Overview](#overview)
- [Requirements](#requirements)
- [Initial Setup](#initial-setup)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)
- [Maintenance](#maintenance)

## Overview

Bot accounts that create pull requests must have **GitHub Actions enabled** to trigger required status checks. Without this, PRs from bot accounts will be permanently blocked.

### Why This Matters

This repository uses GitHub Actions for:
- AI-powered PR quality gates (6 agent reviews)
- Automated testing (Pester tests)
- Path normalization validation
- Session protocol validation
- Spec-to-implementation traceability

All of these are **required status checks** that must pass before merge.

## Requirements

Bot accounts used in this repository must have:

| Requirement | Purpose |
|-------------|---------|
| **GitHub Actions Enabled** | Allows workflows to trigger on bot PRs |
| **Repository Access: Write** | Allows creating PRs and pushing branches |
| **Workflow Permissions: Read and write** | Allows workflows to post comments and update status |

## Initial Setup

### Step 1: Create Bot Account

1. Create a new GitHub account for the bot
2. Add the account as a collaborator to the repository
3. Grant **Write** access

### Step 2: Enable GitHub Actions

**Critical**: This step is required for bot PRs to trigger workflows.

1. Log in as the bot account
2. Navigate to: https://github.com/settings/security_analysis
3. Find the "GitHub Actions" section
4. Click **"Enable GitHub Actions"**
5. Verify the setting is enabled

### Step 3: Configure Workflow Permissions

1. Go to: https://github.com/settings/actions
2. Under "Workflow permissions", select:
   - ✅ **Read and write permissions**
   - ✅ **Allow GitHub Actions to create and approve pull requests**

### Step 4: Authenticate gh CLI

```bash
# Log in as bot account
gh auth login

# Select: GitHub.com
# Select: Login with a web browser
# Follow prompts to authenticate

# Verify authentication
gh auth status
```

### Step 5: Verify Setup

Run the verification script:

```bash
# As bot account
./scripts/Verify-BotAccountActions.ps1

# Should output:
# [Success] Bot can access workflows
# [Success] GitHub Actions appear to be ENABLED
```

## Verification

### Manual Verification

1. **Create a test PR** as the bot:
   ```bash
   # As bot account
   git checkout -b test-bot-setup
   echo "# Test" > test-file.md
   git add test-file.md
   git commit -m "test: verify bot Actions enabled"
   git push origin test-bot-setup
   
   gh pr create \
     --base main \
     --head test-bot-setup \
     --title "test: verify bot Actions enabled" \
     --body "Test PR to verify bot account can trigger workflows"
   ```

2. **Check workflow runs**:
   ```bash
   gh run list --branch test-bot-setup
   
   # Should show workflow runs for:
   # - AI PR Quality Gate
   # - Pester Tests
   # - Validate Path Normalization
   ```

3. **Verify status checks appear**:
   ```bash
   gh pr view --json statusCheckRollup
   
   # Should show all required checks
   ```

4. **Clean up**:
   ```bash
   gh pr close <PR_NUMBER>
   git push origin --delete test-bot-setup
   ```

### Automated Verification

Use the verification script:

```bash
# As bot account
./scripts/Verify-BotAccountActions.ps1

# Or check a specific repository
./scripts/Verify-BotAccountActions.ps1 -Repository "owner/repo"

# Or check from a different account (checks bot PR history)
./scripts/Verify-BotAccountActions.ps1 -BotAccount "rjmurillo-bot"
```

## Troubleshooting

### Problem: "HTTP 422: Actions has been disabled for this user"

**Cause**: GitHub Actions are disabled for the bot account.

**Solution**:
1. Log in as the bot account
2. Go to https://github.com/settings/security_analysis
3. Enable GitHub Actions
4. Retry the operation

### Problem: Workflows don't trigger on bot PRs

**Symptoms**:
- PR shows "Waiting for status checks"
- No workflow runs appear in Actions tab
- `gh run list --branch <branch>` returns empty

**Diagnosis**:
```bash
# Check if bot can access workflows
./scripts/Verify-BotAccountActions.ps1

# Try manual workflow dispatch
gh workflow run ai-pr-quality-gate.yml --field pr_number=<PR_NUMBER>
```

**Solutions**:

1. **Enable Actions** (if HTTP 422 error):
   - Follow [Step 2: Enable GitHub Actions](#step-2-enable-github-actions)

2. **Check workflow permissions**:
   - Go to https://github.com/settings/actions
   - Verify "Read and write permissions" is selected

3. **Verify repository access**:
   ```bash
   gh api repos/owner/repo/collaborators/bot-username
   # Should show "permission": "write" or "admin"
   ```

### Problem: Required status checks never appear

**Cause**: Workflows aren't triggering (see above).

**Workaround**: Recreate PR with a different account:

```bash
# Save PR details
gh pr view <PR_NUMBER> --json body -q .body > /tmp/pr-body.txt
gh pr view <PR_NUMBER> --json title -q .title > /tmp/pr-title.txt

# Close bot PR
gh pr close <PR_NUMBER>

# Switch to personal account
gh auth switch -u your-username

# Recreate PR
gh pr create \
  --base main \
  --head <branch-name> \
  --title "$(cat /tmp/pr-title.txt)" \
  --body "$(cat /tmp/pr-body.txt)"
```

### Problem: "Workflow not found" error

**Cause**: Bot account doesn't have access to the repository.

**Solution**:
1. Add bot as collaborator: Repository Settings → Collaborators
2. Grant **Write** access
3. Bot must accept the invitation

## Maintenance

### Regular Checks

Run verification monthly or after any bot account changes:

```bash
./scripts/Verify-BotAccountActions.ps1
```

### Monitoring

Add to your monitoring dashboard:

```bash
# Check recent bot PRs have workflow runs
gh pr list --author rjmurillo-bot --limit 5 --json number,headRefName

# For each PR, verify workflows ran
gh run list --branch <branch-name>
```

### Documentation Updates

When adding new bot accounts:

1. Follow [Initial Setup](#initial-setup) steps
2. Add bot to this document's bot account list
3. Update repository README if needed

### Bot Account Inventory

| Bot Account | Purpose | Actions Enabled | Last Verified |
|-------------|---------|-----------------|---------------|
| `rjmurillo-bot` | Automated PRs | ✅ Yes | 2025-01-XX |

## Best Practices

### For Bot Account Owners

- ✅ **Enable Actions immediately** after creating bot account
- ✅ **Test with a dummy PR** before production use
- ✅ **Document bot purpose** in repository
- ✅ **Use PAT with minimal scopes** (repo, workflow)
- ✅ **Rotate PAT regularly** (every 90 days)

### For Repository Maintainers

- ✅ **Verify bot setup** before granting write access
- ✅ **Monitor bot PR success rate** (should be 100%)
- ✅ **Document bot accounts** in repository
- ✅ **Review bot permissions** quarterly

### For CI/CD Pipelines

- ✅ **Use bot account for automated PRs**
- ✅ **Handle workflow failures gracefully**
- ✅ **Log bot operations** for debugging
- ✅ **Test bot setup** in staging first

## Security Considerations

### PAT (Personal Access Token) Management

Bot accounts should use PATs with minimal scopes:

```bash
# Required scopes for bot PRs
- repo (full control of private repositories)
- workflow (update GitHub Action workflows)
```

Store PATs securely:
- ✅ Use GitHub Secrets for CI/CD
- ✅ Use environment variables locally
- ✅ Never commit PATs to repository
- ✅ Rotate PATs every 90 days

### Access Control

- ✅ Grant **Write** access only (not Admin)
- ✅ Use branch protection rules
- ✅ Require PR reviews for bot PRs (if needed)
- ✅ Monitor bot activity regularly

## Related Documentation

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Managing GitHub Actions settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository)
- [About required status checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches#require-status-checks-before-merging)

## Support

If you encounter issues:

1. Run verification script: `./scripts/Verify-BotAccountActions.ps1`
2. Check [Troubleshooting](#troubleshooting) section
3. Review workflow logs: `gh run view <run-id>`
4. Open an issue with verification script output

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2025-01-XX | Initial documentation | Analysis of Issue #208 |
