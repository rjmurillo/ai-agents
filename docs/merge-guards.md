# Merge Guards and Branch Protection Recommendations

## Overview

This document provides recommendations for GitHub branch protection rules to enforce technical guardrails at the merge gate. These are Phase 5 recommendations from Issue #230.

## Current State

The repository currently has:

- ✅ Pre-commit hooks (session log, skill detection, test coverage)
- ✅ CI validation (PR description, QA reports, session protocol)
- ⚠️ No branch protection enforcement at merge gate
- ⚠️ PRs can be merged with failing validations using admin override

## Recommended Branch Protection Rules

### For `main` Branch

#### Required Status Checks

Configure these CI checks as **required** before merge:

1. **PR Validation** (`.github/workflows/pr-validation.yml`)
   - Blocks: PR description mismatches (CRITICAL)
   - Warns: Missing QA reports

2. **Session Protocol Validation** (`.github/workflows/ai-session-protocol.yml`)
   - Blocks: Session End protocol violations (MUST requirements)
   - Required: For PRs changing `.agents/sessions/*.md`

3. **Pester Tests** (`.github/workflows/pester-tests.yml`)
   - Blocks: PowerShell test failures
   - Required: For PRs changing `scripts/**`

4. **AI Quality Gate** (`.github/workflows/ai-pr-quality-gate.yml`)
   - Blocks: Analyst/QA/Security CRITICAL_FAIL verdicts
   - Required: For PRs changing code

#### Require Branches to be Up to Date

**Enabled**: ✅

**Rationale**: Ensures validation runs against latest `main`, prevents race conditions

#### Require Approvals

**Minimum**: 1 approval

**Dismiss Stale Reviews**: ✅

**Require Review from Code Owners**: ✅ (if CODEOWNERS file exists)

**Rationale**: Human oversight for autonomous agent work

#### Require Conversation Resolution

**Enabled**: ✅

**Rationale**: Prevents merging with unresolved review comments (addresses PR #226 failure)

#### Additional Restrictions

**Restrict Pushes**: Allowed actors only

**Allow Force Pushes**: ❌

**Allow Deletions**: ❌

**Require Linear History**: ✅ (optional, prevents complex merge commits)

### Configuration Steps

#### Via GitHub UI

1. Go to repository **Settings** → **Branches**
2. Add rule for `main` branch
3. Enable:
   - ✅ Require a pull request before merging
   - ✅ Require approvals (1)
   - ✅ Dismiss stale pull request approvals when new commits are pushed
   - ✅ Require status checks to pass before merging
   - ✅ Require branches to be up to date before merging
   - ✅ Require conversation resolution before merging
   - ✅ Do not allow bypassing the above settings (for admins)
4. Add status checks:
   - `PR Validation / Validate PR`
   - `Session Protocol Validation / validate` (matrix jobs)
   - `Pester Tests / test`
   - `AI Quality Gate / aggregate`
5. Save changes

#### Via GitHub CLI

```bash
# Create branch protection rule
gh api repos/:owner/:repo/branches/main/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["PR Validation / Validate PR","Session Protocol Validation / validate","Pester Tests / test","AI Quality Gate / aggregate"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"required_approving_review_count":1,"dismiss_stale_reviews":true}' \
  --field restrictions=null \
  --field required_conversation_resolution=true
```

#### Via Terraform

```hcl
resource "github_branch_protection" "main" {
  repository_id = github_repository.repo.node_id
  pattern       = "main"

  required_status_checks {
    strict   = true
    contexts = [
      "PR Validation / Validate PR",
      "Session Protocol Validation / validate",
      "Pester Tests / test",
      "AI Quality Gate / aggregate"
    ]
  }

  required_pull_request_reviews {
    required_approving_review_count = 1
    dismiss_stale_reviews           = true
  }

  enforce_admins              = true
  require_conversation_resolution = true
  allow_force_pushes          = false
  allow_deletions             = false
}
```

## Special Handling for Security Comments

### Problem

PR #226 merged with security comments dismissed as "won't fix" without proper review.

### Recommendation

Implement **CODEOWNERS** file with security review requirement:

```text
# Security-sensitive files require security agent approval
.github/workflows/*.yml @security-team
**/*Auth* @security-team
**/security/** @security-team
```

### Workflow Enhancement

Enhance `.github/workflows/pr-validation.yml` to detect security dismissals:

```yaml
- name: Check Security Review Status
  shell: pwsh
  run: |
    $comments = gh api "/repos/${{ github.repository }}/pulls/${{ env.PR_NUMBER }}/reviews" | ConvertFrom-Json
    
    $securityDismissals = $comments | Where-Object {
      $_.body -match '\b(won''t fix|WONT_FIX)\b' -and
      $_.body -match '\b(security|vulnerability|CVE)\b'
    }
    
    if ($securityDismissals.Count -gt 0) {
      # Check if security team approved
      $securityApproval = $comments | Where-Object {
        $_.user.login -eq 'security-agent' -and
        $_.state -eq 'APPROVED'
      }
      
      if (-not $securityApproval) {
        Write-Error "Security comments dismissed without security agent approval"
        exit 1
      }
    }
```

## Testing Branch Protection

### Test Scenarios

#### Scenario 1: PR Description Mismatch

**Setup**: Create PR claiming file changes that aren't in diff

**Expected**: CI fails, merge blocked

**Verify**: PR cannot be merged until description is fixed

#### Scenario 2: Missing Session Log

**Setup**: Create PR with `.agents/` changes but no session log

**Expected**: Pre-commit hook blocks, or if bypassed, CI fails

**Verify**: Merge blocked until session log is added and validated

#### Scenario 3: Unresolved Review Comments

**Setup**: Create PR, add review comment, leave unresolved

**Expected**: Merge blocked

**Verify**: Must resolve or dismiss comment to merge

#### Scenario 4: Security Dismissal

**Setup**: Create PR, add security comment, dismiss without approval

**Expected**: CI detects dismissal, blocks merge

**Verify**: Requires security team approval to proceed

### Validation Commands

```bash
# Check branch protection status
gh api repos/:owner/:repo/branches/main/protection | jq .

# List required status checks
gh api repos/:owner/:repo/branches/main/protection/required_status_checks | jq .contexts

# Check if PR is mergeable
gh pr view <number> --json mergeable,mergeStateStatus
```

## Rollout Plan

### Phase 1: Soft Launch (Week 1)

**Goal**: Collect data without blocking

**Actions**:

1. Deploy all CI validations (already done)
2. Monitor failure rates
3. Fix false positives
4. Update documentation

**Success Criteria**: <5% false positive rate

### Phase 2: Warning Mode (Week 2)

**Goal**: Warn but don't block

**Actions**:

1. Add workflow step to post warning comments
2. Track dismissal patterns
3. Refine detection logic

**Success Criteria**: Team familiar with warnings, <2% false positive rate

### Phase 3: Enforcement (Week 3+)

**Goal**: Enable branch protection

**Actions**:

1. Enable required status checks
2. Enable conversation resolution requirement
3. Monitor merge blockage rate
4. Provide bypass process for emergencies

**Success Criteria**: <10% merge blockage rate, <1% false positives

## Emergency Bypass Process

When merge is blocked but code is correct:

### Option 1: Admin Override

**When**: False positive confirmed, production incident

**Process**:

1. Document reason in PR comment
2. Tag security/QA agent for post-merge review
3. Admin bypasses protection
4. Merge PR
5. Create follow-up issue for false positive fix

**Audit**: All overrides logged in GitHub audit log

### Option 2: Temporary Rule Relaxation

**When**: Multiple PRs blocked by same false positive

**Process**:

1. Create issue documenting problem
2. Temporarily disable failing check
3. Merge blocked PRs
4. Fix check
5. Re-enable check
6. Close issue

**Duration**: Maximum 24 hours

## Monitoring and Metrics

### Key Metrics to Track

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Merge blockage rate | <10% | >20% |
| False positive rate | <1% | >5% |
| Override usage | <5% | >10% |
| Security dismissals without review | 0 | >0 |
| Session protocol violations | <5% | >10% |
| Time to merge (P50) | <4 hours | >24 hours |

### Dashboard Queries

```bash
# Merge blockage rate (last 30 days)
gh api "search/issues?q=repo:owner/repo+is:pr+is:closed+base:main+closed:>$(date -d '30 days ago' +%Y-%m-%d)" | jq '.items | length'

# PRs merged with overrides
gh api "repos/owner/repo/pulls?state=closed&sort=updated&direction=desc" | jq '[.[] | select(.merged_at and .mergeable_state == "dirty")] | length'

# Average time to merge
gh pr list --state merged --limit 100 --json createdAt,mergedAt | jq '[.[] | (.mergedAt | fromdateiso8601) - (.createdAt | fromdateiso8601)] | add / length / 3600'
```

## Related Documents

- [Technical Guardrails Guide](technical-guardrails.md)
- [SESSION-PROTOCOL.md](../.agents/SESSION-PROTOCOL.md)
- [Issue #230](https://github.com/rjmurillo/ai-agents/issues/230)
- [Retrospective: PR #226](../.agents/retrospective/2025-12-22-pr-226-premature-merge-failure.md)

## References

- [GitHub Branch Protection Documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [Required Status Checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches#require-status-checks-before-merging)
- [CODEOWNERS Documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
