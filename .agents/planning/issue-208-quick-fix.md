# Quick Fix: Unblock PR #208

**Issue**: PR #208 blocked - no workflows running  
**Root Cause**: `rjmurillo-bot` has GitHub Actions disabled  
**Time to Fix**: 5-10 minutes

## Option 1: Enable Actions (Permanent Fix) ⭐

**Best for**: Long-term solution, maintains bot attribution

### Steps

1. **Log in as rjmurillo-bot**:
   - Go to https://github.com/login
   - Log in with bot account credentials

2. **Enable Actions**:
   - Go to https://github.com/settings/security_analysis
   - Find "GitHub Actions" section
   - Click "Enable GitHub Actions"

3. **Trigger workflows for PR #208**:
   ```bash
   gh workflow run ai-pr-quality-gate.yml \
     --repo rjmurillo/ai-agents \
     --field pr_number=208
   ```

4. **Verify**:
   ```bash
   # Check if workflows are running
   gh run list --repo rjmurillo/ai-agents --branch docs/reconcile-kiro-plan
   ```

5. **Done!** ✅
   - Workflows will run
   - Required checks will appear
   - PR can proceed to merge

---

## Option 2: Recreate PR (Temporary Workaround)

**Best for**: When you can't access bot account immediately

### Steps

1. **Save PR details**:
   ```bash
   gh pr view 208 --json body -q .body > /tmp/pr-body.txt
   gh pr view 208 --json title -q .title > /tmp/pr-title.txt
   ```

2. **Close PR #208**:
   ```bash
   gh pr close 208 --comment "Recreating with different account due to Actions issue"
   ```

3. **Switch to rjmurillo account**:
   ```bash
   gh auth switch -u rjmurillo
   ```

4. **Recreate PR**:
   ```bash
   gh pr create \
     --repo rjmurillo/ai-agents \
     --base main \
     --head docs/reconcile-kiro-plan \
     --title "$(cat /tmp/pr-title.txt)" \
     --body "$(cat /tmp/pr-body.txt)

   Note: Recreated from PR #208 due to bot Actions issue."
   ```

5. **Enable auto-merge**:
   ```bash
   NEW_PR=$(gh pr list --head docs/reconcile-kiro-plan --json number -q '.[0].number')
   gh pr merge $NEW_PR --auto --squash
   ```

6. **Done!** ✅
   - New PR will trigger workflows
   - Required checks will run
   - Auto-merge will complete when checks pass

---

## Verification

After either option, verify workflows are running:

```bash
# Check workflow runs
gh run list --repo rjmurillo/ai-agents --branch docs/reconcile-kiro-plan

# Should show runs for:
# - AI PR Quality Gate
# - Pester Tests
# - Validate Path Normalization
# - (and others)
```

## Troubleshooting

### "HTTP 422: Actions has been disabled for this user"

**Cause**: Actions still disabled for bot account  
**Fix**: Complete Option 1 steps above

### "No workflow runs found"

**Cause**: Workflows haven't triggered yet  
**Fix**: Wait 1-2 minutes, or trigger manually:

```bash
gh workflow run ai-pr-quality-gate.yml --field pr_number=208
```

### "Required checks still not appearing"

**Cause**: Workflows may be queued or running  
**Fix**: Check workflow status:

```bash
gh run list --branch docs/reconcile-kiro-plan
gh run view <run-id>  # Use ID from list command
```

## Next Steps

After PR #208 is unblocked:

1. ✅ **Document bot account requirements** (see `.agents/planning/issue-208-action-plan.md`)
2. ✅ **Verify other bot accounts** have Actions enabled
3. ✅ **Add monitoring** for bot account health

## Need Help?

- **Full Analysis**: `.agents/analysis/issue-208-bot-actions-disabled.md`
- **Detailed Action Plan**: `.agents/planning/issue-208-action-plan.md`
- **Issue**: #208
