# Issue #208 Resolution Checklist

**Issue**: GitHub Actions disabled for rjmurillo-bot - blocks PR #208  
**Status**: Ready to execute  
**Estimated Time**: 15 minutes

## Pre-Flight Check

- [ ] Have access to `rjmurillo-bot` account credentials
- [ ] Have `gh` CLI installed and working
- [ ] Have repository access (rjmurillo/ai-agents)
- [ ] PR #208 is still open and blocked

## Option A: Enable Actions (Recommended)

### Phase 1: Enable Actions for Bot Account (5 min)

- [ ] **Step 1.1**: Log in as `rjmurillo-bot`
  ```bash
  gh auth login
  # Select: GitHub.com
  # Select: Login with a web browser
  # Authenticate as rjmurillo-bot
  ```

- [ ] **Step 1.2**: Verify authentication
  ```bash
  gh auth status
  # Should show: Logged in to github.com as rjmurillo-bot
  ```

- [ ] **Step 1.3**: Navigate to Actions settings
  - Open: https://github.com/settings/security_analysis
  - Or: Settings → Code security and analysis

- [ ] **Step 1.4**: Enable GitHub Actions
  - Find "GitHub Actions" section
  - Click "Enable GitHub Actions" button
  - Verify setting is enabled

- [ ] **Step 1.5**: Configure workflow permissions
  - Go to: https://github.com/settings/actions
  - Select: "Read and write permissions"
  - Check: "Allow GitHub Actions to create and approve pull requests"
  - Click "Save"

### Phase 2: Verify Bot Setup (3 min)

- [ ] **Step 2.1**: Run verification script
  ```bash
  ./scripts/Verify-BotAccountActions.ps1
  ```
  - Expected: `[Success] GitHub Actions appear to be ENABLED`

- [ ] **Step 2.2**: Test manual workflow dispatch
  ```bash
  gh workflow run ai-pr-quality-gate.yml \
    --repo rjmurillo/ai-agents \
    --field pr_number=208
  ```
  - Expected: No HTTP 422 error
  - Expected: Workflow run created

- [ ] **Step 2.3**: Verify workflow started
  ```bash
  gh run list --repo rjmurillo/ai-agents --branch docs/reconcile-kiro-plan
  ```
  - Expected: At least 1 workflow run shown

### Phase 3: Trigger All Required Workflows (5 min)

- [ ] **Step 3.1**: Check which workflows need triggering
  ```bash
  gh pr view 208 --json statusCheckRollup
  ```

- [ ] **Step 3.2**: Trigger AI PR Quality Gate (if not already running)
  ```bash
  gh workflow run ai-pr-quality-gate.yml --field pr_number=208
  ```

- [ ] **Step 3.3**: Wait for workflows to complete
  ```bash
  gh run watch  # Watch latest run
  ```

- [ ] **Step 3.4**: Verify all checks appear on PR
  ```bash
  gh pr view 208
  ```
  - Expected: All 11 required checks visible
  - Expected: Checks running or completed

### Phase 4: Verify PR Can Proceed (2 min)

- [ ] **Step 4.1**: Check PR status
  ```bash
  gh pr view 208 --json statusCheckRollup,mergeable
  ```

- [ ] **Step 4.2**: Verify auto-merge is enabled
  ```bash
  gh pr view 208 --json autoMergeRequest
  ```

- [ ] **Step 4.3**: If auto-merge not enabled, enable it
  ```bash
  gh pr merge 208 --auto --squash
  ```

- [ ] **Step 4.4**: Monitor PR until merge
  - PR should merge automatically when all checks pass

## Option B: Recreate PR (Alternative)

**Use only if Option A is blocked (no bot account access)**

### Phase 1: Save PR Details (2 min)

- [ ] **Step 1.1**: Save PR body
  ```bash
  gh pr view 208 --json body -q .body > /tmp/pr-208-body.txt
  ```

- [ ] **Step 1.2**: Save PR title
  ```bash
  gh pr view 208 --json title -q .title > /tmp/pr-208-title.txt
  ```

- [ ] **Step 1.3**: Note branch name
  ```bash
  gh pr view 208 --json headRefName -q .headRefName
  # Should be: docs/reconcile-kiro-plan
  ```

### Phase 2: Close and Recreate (5 min)

- [ ] **Step 2.1**: Close PR #208
  ```bash
  gh pr close 208 --comment "Closing to recreate with different account due to Actions permissions issue. Will recreate immediately."
  ```

- [ ] **Step 2.2**: Switch to rjmurillo account
  ```bash
  gh auth switch -u rjmurillo
  # Or: gh auth login (and authenticate as rjmurillo)
  ```

- [ ] **Step 2.3**: Verify authentication
  ```bash
  gh auth status
  # Should show: Logged in to github.com as rjmurillo
  ```

- [ ] **Step 2.4**: Recreate PR
  ```bash
  gh pr create \
    --repo rjmurillo/ai-agents \
    --base main \
    --head docs/reconcile-kiro-plan \
    --title "$(cat /tmp/pr-208-title.txt)" \
    --body "$(cat /tmp/pr-208-body.txt)

  **Note**: Recreated from PR #208 due to Actions permissions issue with bot account."
  ```

- [ ] **Step 2.5**: Note new PR number
  ```bash
  NEW_PR=$(gh pr list --head docs/reconcile-kiro-plan --json number -q '.[0].number')
  echo "New PR: #$NEW_PR"
  ```

### Phase 3: Verify and Enable Auto-Merge (3 min)

- [ ] **Step 3.1**: Verify workflows triggered
  ```bash
  gh run list --branch docs/reconcile-kiro-plan
  ```
  - Expected: Multiple workflow runs shown

- [ ] **Step 3.2**: Check PR status
  ```bash
  gh pr view $NEW_PR
  ```
  - Expected: Status checks running

- [ ] **Step 3.3**: Enable auto-merge
  ```bash
  gh pr merge $NEW_PR --auto --squash
  ```

- [ ] **Step 3.4**: Monitor PR
  - PR should merge automatically when checks pass

## Post-Resolution Tasks

### Immediate (P1)

- [ ] **Update Issue #208**
  - Comment with resolution details
  - Close issue as resolved
  - Link to this checklist

- [ ] **Document in HANDOFF.md**
  - Add note about bot Actions being enabled
  - Update status of PR #208

### Short-Term (P2)

- [ ] **Update Documentation**
  - Review `docs/bot-account-setup.md`
  - Add to CONTRIBUTING.md if needed

- [ ] **Create Monitoring**
  - Add bot account verification to CI
  - Set up alerts for bot PR failures

### Long-Term (P3)

- [ ] **Review Other Bot Accounts**
  - Check if other bots exist
  - Verify Actions enabled for all

- [ ] **Add to Onboarding**
  - Include bot setup in new contributor guide
  - Add to repository setup checklist

## Verification Criteria

### Success Criteria

- ✅ No HTTP 422 errors when triggering workflows
- ✅ Workflows appear in Actions tab for bot PRs
- ✅ All 11 required status checks run on PR #208 (or new PR)
- ✅ PR can proceed to merge
- ✅ Auto-merge completes successfully

### Failure Indicators

- ❌ HTTP 422 error persists
- ❌ Workflows still don't trigger
- ❌ Required checks don't appear
- ❌ PR remains blocked

## Rollback Plan

If issues occur:

- [ ] **Rollback Step 1**: Disable Actions for bot (if causing problems)
  - Go to https://github.com/settings/security_analysis
  - Disable GitHub Actions

- [ ] **Rollback Step 2**: Use personal account for PRs
  - Document in team procedures
  - Update bot usage guidelines

- [ ] **Rollback Step 3**: Escalate to organization admin
  - Check organization policies
  - Request policy exception if needed

## Troubleshooting

### Issue: HTTP 422 persists after enabling Actions

**Check**:
```bash
# Verify Actions are actually enabled
gh api /users/rjmurillo-bot --jq '.type'
# Should return: "User"

# Check organization policies
gh api /orgs/<org>/actions/permissions
```

**Solution**: May need organization admin to enable Actions at org level

### Issue: Workflows trigger but fail immediately

**Check**:
```bash
# View workflow run details
gh run view <run-id>

# Check workflow logs
gh run view <run-id> --log
```

**Solution**: Address specific workflow failures (separate from Actions enablement)

### Issue: Some checks appear, others don't

**Check**:
```bash
# List all workflows
gh workflow list

# Check if specific workflow is active
gh workflow view <workflow-name>
```

**Solution**: May need to trigger specific workflows manually

## Time Tracking

| Phase | Estimated | Actual | Notes |
|-------|-----------|--------|-------|
| Enable Actions | 5 min | | |
| Verify Setup | 3 min | | |
| Trigger Workflows | 5 min | | |
| Verify PR | 2 min | | |
| **Total** | **15 min** | | |

## Sign-Off

- [ ] **Executed by**: ________________
- [ ] **Date**: ________________
- [ ] **Result**: ☐ Success ☐ Partial ☐ Failed
- [ ] **Notes**: ________________

## References

- **Issue**: #208
- **PR**: #208 (or new PR number: _____)
- **Analysis**: `.agents/analysis/issue-208-bot-actions-disabled.md`
- **Action Plan**: `.agents/planning/issue-208-action-plan.md`
- **Quick Fix**: `.agents/planning/issue-208-quick-fix.md`
- **Verification Script**: `scripts/Verify-BotAccountActions.ps1`
- **Documentation**: `docs/bot-account-setup.md`
