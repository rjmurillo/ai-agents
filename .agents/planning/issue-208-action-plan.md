# Action Plan: Fix rjmurillo-bot Actions Disabled Issue

**Issue**: #208 - GitHub Actions disabled for rjmurillo-bot account  
**Priority**: P0 (blocks all CI/CD for bot-created PRs)  
**Owner**: Repository Admin  
**Status**: Ready for execution

## Executive Summary

PR #208 is blocked because the `rjmurillo-bot` account has GitHub Actions disabled at the account level. This prevents all workflow triggers, causing required status checks to never run. The solution is to enable Actions for the bot account.

## Immediate Actions (P0)

### 1. Enable Actions for rjmurillo-bot Account

**Owner**: Account owner with access to `rjmurillo-bot`  
**Estimated Time**: 5 minutes  
**Blocking**: PR #208

**Steps**:

1. **Log in as rjmurillo-bot**:
   ```bash
   # If using gh CLI
   gh auth login
   # Select: GitHub.com
   # Select: Login with a web browser
   # Follow prompts to authenticate as rjmurillo-bot
   ```

2. **Navigate to Actions Settings**:
   - Go to: https://github.com/settings/security_analysis
   - Or: Settings → Code security and analysis

3. **Enable GitHub Actions**:
   - Look for "GitHub Actions" section
   - If Actions are disabled, there should be an "Enable" button
   - Click "Enable GitHub Actions"

4. **Verify Permissions**:
   - Check that Actions permissions are set to "Allow all actions and reusable workflows"
   - Or at minimum: "Allow actions created by GitHub" + "Allow actions by Marketplace verified creators"

5. **Verify Repository Access**:
   ```bash
   # As rjmurillo-bot
   gh auth status
   
   # Verify repository access
   gh repo view rjmurillo/ai-agents
   ```

**Verification**:
```bash
# Test manual workflow dispatch
gh workflow run ai-pr-quality-gate.yml \
  --repo rjmurillo/ai-agents \
  --field pr_number=208

# Should succeed without HTTP 422 error
```

**Success Criteria**:
- ✅ No HTTP 422 error when running workflow dispatch
- ✅ Workflows appear in Actions tab
- ✅ Can trigger workflows manually

### 2. Trigger Workflows for PR #208

**Owner**: Repository maintainer  
**Estimated Time**: 2 minutes  
**Depends On**: Step 1 completed

**Steps**:

1. **Trigger AI PR Quality Gate**:
   ```bash
   gh workflow run ai-pr-quality-gate.yml \
     --repo rjmurillo/ai-agents \
     --field pr_number=208
   ```

2. **Verify Workflow Runs**:
   ```bash
   # Check workflow runs for the branch
   gh run list \
     --repo rjmurillo/ai-agents \
     --branch docs/reconcile-kiro-plan
   
   # Should show at least 1 run
   ```

3. **Monitor Workflow Execution**:
   ```bash
   # Watch the latest run
   gh run watch
   ```

**Success Criteria**:
- ✅ All 11 required status checks appear on PR #208
- ✅ Workflows execute successfully
- ✅ PR shows "All checks have passed" (or specific failures to address)

## Alternative: Immediate Workaround (If Step 1 Blocked)

**Use Only If**: Cannot enable Actions for `rjmurillo-bot` immediately

### Recreate PR #208 Using rjmurillo Account

**Owner**: Repository maintainer  
**Estimated Time**: 5 minutes  
**Risk**: Changes PR attribution

**Steps**:

1. **Save PR #208 Details**:
   ```bash
   # Save PR body for reference
   gh pr view 208 --json body -q .body > /tmp/pr-208-body.txt
   
   # Save PR title
   gh pr view 208 --json title -q .title > /tmp/pr-208-title.txt
   ```

2. **Close PR #208**:
   ```bash
   gh pr close 208 --comment "Closing to recreate with different account due to Actions permissions issue. Will recreate immediately."
   ```

3. **Switch to rjmurillo Account**:
   ```bash
   gh auth switch -u rjmurillo
   # Or: gh auth login (and authenticate as rjmurillo)
   ```

4. **Recreate PR**:
   ```bash
   gh pr create \
     --repo rjmurillo/ai-agents \
     --base main \
     --head docs/reconcile-kiro-plan \
     --title "$(cat /tmp/pr-208-title.txt)" \
     --body "$(cat /tmp/pr-208-body.txt)

   **Note**: Recreated from PR #208 due to Actions permissions issue with bot account."
   ```

5. **Enable Auto-Merge**:
   ```bash
   # Get new PR number
   NEW_PR=$(gh pr list --head docs/reconcile-kiro-plan --json number -q '.[0].number')
   
   # Enable auto-merge
   gh pr merge $NEW_PR --auto --squash
   ```

**Success Criteria**:
- ✅ New PR created with same content
- ✅ Workflows trigger automatically
- ✅ All required checks run
- ✅ Auto-merge enabled

## Follow-Up Actions (P1-P2)

### 3. Document Bot Account Configuration (P1)

**Owner**: Documentation maintainer  
**Estimated Time**: 15 minutes

**Steps**:

1. **Update CONTRIBUTING.md**:
   ```bash
   # Add section about bot accounts
   ```

2. **Create Bot Account Setup Guide**:
   - Document required permissions
   - Document Actions enablement
   - Document verification steps

3. **Update Repository README**:
   - Add note about bot account requirements
   - Link to setup guide

**Deliverable**: Documentation PR with bot account requirements

### 4. Add Bot Account Verification to CI (P2)

**Owner**: DevOps  
**Estimated Time**: 30 minutes

**Steps**:

1. **Create Verification Script**:
   ```bash
   # scripts/verify-bot-account.ps1
   # Checks if bot account has Actions enabled
   ```

2. **Add to Pre-PR Checklist**:
   - Verify bot account configuration
   - Test workflow triggers

3. **Add Monitoring**:
   - Alert if bot PRs don't trigger workflows
   - Dashboard for bot account health

**Deliverable**: Monitoring and verification tooling

### 5. Review Other Bot Accounts (P2)

**Owner**: Repository admin  
**Estimated Time**: 10 minutes

**Steps**:

1. **List All Bot Accounts**:
   ```bash
   # Check repository collaborators
   gh api repos/rjmurillo/ai-agents/collaborators \
     --jq '.[] | select(.type == "Bot" or (.login | contains("bot"))) | .login'
   ```

2. **Verify Actions Enabled**:
   - Check each bot account
   - Enable Actions if needed

3. **Document Bot Accounts**:
   - Create inventory of bot accounts
   - Document purpose and permissions

**Deliverable**: Bot account inventory and configuration status

## Testing & Verification

### Test Plan

After enabling Actions for `rjmurillo-bot`:

1. **Create Test PR**:
   ```bash
   # As rjmurillo-bot
   git checkout -b test-bot-actions
   echo "# Test" > test-file.md
   git add test-file.md
   git commit -m "test: verify bot Actions enabled"
   git push origin test-bot-actions
   
   gh pr create \
     --base main \
     --head test-bot-actions \
     --title "test: verify bot Actions enabled" \
     --body "Test PR to verify rjmurillo-bot can trigger workflows"
   ```

2. **Verify Workflows Trigger**:
   ```bash
   # Check workflow runs
   gh run list --branch test-bot-actions
   
   # Should show workflow runs
   ```

3. **Verify Manual Dispatch**:
   ```bash
   # Get test PR number
   TEST_PR=$(gh pr list --head test-bot-actions --json number -q '.[0].number')
   
   # Trigger workflow manually
   gh workflow run ai-pr-quality-gate.yml --field pr_number=$TEST_PR
   
   # Should succeed without errors
   ```

4. **Clean Up**:
   ```bash
   # Close test PR
   gh pr close $TEST_PR
   
   # Delete test branch
   git push origin --delete test-bot-actions
   ```

### Success Criteria

- ✅ Test PR triggers all workflows automatically
- ✅ Manual workflow dispatch succeeds
- ✅ All required status checks appear
- ✅ No HTTP 422 errors
- ✅ PR #208 can proceed to merge

## Rollback Plan

If enabling Actions causes issues:

1. **Disable Actions for rjmurillo-bot**:
   - Go to https://github.com/settings/security_analysis
   - Disable GitHub Actions

2. **Use Alternative Account**:
   - Switch to `rjmurillo` account for PRs
   - Document in team procedures

3. **Review Organization Policies**:
   - Check if organization policies prevent bot Actions
   - Escalate to organization admin if needed

## Communication Plan

### Stakeholders

- **Repository Maintainers**: Need to know about the fix
- **Bot Users**: Need to know about account changes
- **PR #208 Author**: Need to know about PR status

### Updates

1. **Issue #208 Comment**:
   ```markdown
   ## Status Update
   
   Root cause identified: `rjmurillo-bot` account has GitHub Actions disabled.
   
   **Resolution**: Enabling Actions for the bot account.
   
   **Timeline**: 
   - Enable Actions: [ETA]
   - Trigger workflows: Immediately after
   - PR ready to merge: [ETA]
   
   See action plan: .agents/planning/issue-208-action-plan.md
   ```

2. **PR #208 Comment** (after fix):
   ```markdown
   ✅ **Actions Enabled**
   
   GitHub Actions have been enabled for `rjmurillo-bot`. Workflows are now running.
   
   Status: Waiting for checks to complete.
   ```

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Organization policy blocks bot Actions | Low | High | Escalate to org admin |
| Workflows fail after enabling | Low | Medium | Review workflow logs, fix issues |
| PR #208 has other issues | Medium | Low | Address issues as they appear |
| Bot account access unavailable | Low | High | Use workaround (recreate PR) |

## Timeline

| Task | Duration | Dependencies | Owner |
|------|----------|--------------|-------|
| Enable Actions for bot | 5 min | Account access | Admin |
| Trigger workflows for PR #208 | 2 min | Actions enabled | Maintainer |
| Verify workflows complete | 10 min | Workflows triggered | Maintainer |
| Document bot requirements | 15 min | None | Documentation |
| Create verification tooling | 30 min | None | DevOps |

**Total Time to Unblock PR #208**: ~15 minutes  
**Total Time for Complete Solution**: ~1 hour

## References

- **Analysis**: `.agents/analysis/issue-208-bot-actions-disabled.md`
- **Issue**: #208
- **Affected PR**: #208
- **GitHub Docs**: [Managing GitHub Actions settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository)
