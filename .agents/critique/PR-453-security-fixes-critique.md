# Security Fixes Review: PR #453

## Verdict

**NEEDS REVISION**

Confidence: HIGH
Rationale: Critical GraphQL injection vulnerability found. Input validation incomplete. ADR-015 compliance verification needed.

## Summary

PR #453 addresses three security issues identified in ADR-015:
1. GraphQL injection prevention via parameterized queries
2. Input validation for branch names (command injection prevention)
3. Removal of file-based locking per ADR-015 Decision 1

Two critical issues block approval:
1. **GraphQL injection still present** in Resolve-PRReviewThread.ps1
2. **Missing rate limit validation** per ADR-015 Decision 2

## Issues Found

### Critical (Must Fix)

- [ ] **GraphQL Injection in Resolve-PRReviewThread.ps1**
  - **Location**: Lines 41-50, 84-104
  - **Issue**: Two GraphQL queries use string interpolation instead of variables
  - **Attack Vector**: Malicious ThreadId could inject arbitrary GraphQL
  - **Evidence**:
    - Line 43: `mutation { resolveReviewThread(input: {threadId: "$Id"}) ...`
    - Line 86: `repository(owner: "$($repo.owner.login)", name: "$($repo.name)") ...`
  - **Fix Required**: Convert to parameterized queries like Get-UnresolvedReviewThreads.ps1
  - **Severity**: HIGH - same class of vulnerability that PR claims to fix

- [ ] **Missing Rate Limit Validation**
  - **Location**: ADR-015 Decision 2 requires multi-resource rate limiting
  - **Issue**: Current `Test-RateLimitSafe` only checks core and graphql resources
  - **ADR Requirement**: Must check search, code_scanning_autofix, audit_log_streaming, code_search
  - **Evidence**: ADR-015 lines 48-70 specify thresholds for 5 resources, current implementation checks 2
  - **Severity**: MEDIUM - could cause silent failures during hourly automation

### Important (Should Fix)

- [ ] **Incomplete Branch Name Validation**
  - **Location**: Resolve-PRConflicts.ps1:239, 244
  - **Issue**: Validates BranchName and TargetBranch but not all git operations
  - **Gap**: Lines 264, 268, 274, 280 use validated branches but line 368 uses unvalidated worktree path components
  - **Risk**: MEDIUM - path traversal already mitigated by Get-SafeWorktreePath, but defense-in-depth incomplete

- [ ] **Input Validation Missing for ThreadId**
  - **Location**: Resolve-PRReviewThread.ps1:39 (before GraphQL injection fix)
  - **Issue**: ThreadId parameter not validated before use in mutation
  - **Attack Surface**: External input from PR review threads
  - **Recommendation**: Add Test-SafeThreadId function with GraphQL ID format validation

### Minor (Consider)

- [ ] **Error Handling Inconsistency**
  - **Location**: Get-UnresolvedReviewThreads.ps1:119-122 vs Resolve-PRReviewThread.ps1:52-56
  - **Issue**: Different error handling patterns for identical `gh api graphql` calls
  - **Recommendation**: Standardize on `Write-Warning` + return empty result pattern

## Security Analysis by Component

### Component 1: Get-UnresolvedReviewThreads.ps1

**Status**: [PASS]

GraphQL injection fix complete and correct:
- Line 118: Uses `-f owner="$Owner" -f name="$Repo" -F prNumber=$PR`
- Query (lines 98-116): Variables declared in query signature
- No string interpolation in GraphQL query body

Input validation: N/A (PR number is int, Owner/Repo from git remote)

### Component 2: Resolve-PRConflicts.ps1

**Status**: [PASS with note]

Branch name validation implemented:
- Lines 239, 244: Both BranchName and TargetBranch validated via Test-SafeBranchName
- Lines 88-132: Comprehensive validation function
- Blocks: empty/whitespace, leading hyphen, path traversal, control chars, git special chars, shell metacharacters

Path traversal protection:
- Lines 141-170: Get-SafeWorktreePath validates PR number and prevents directory escape
- Line 157: Resolve-Path ensures base path exists
- Line 165: Validates resolved path starts with base (canonicalization check)

ADR-015 compliance: Full (implements Decision 3)

**Note**: File does not include file-based locking (correct per ADR-015 Decision 1)

### Component 3: Invoke-PRMaintenance.ps1

**Status**: [PARTIAL PASS]

GraphQL injection fix complete:
- Line 283: Uses `-f owner="$Owner" -f name="$Repo" -F limit=$Limit`
- Query (lines 234-281): Variables declared in query signature

File-based locking removed: [PASS]
- No references to Enter-ScriptLock or Exit-ScriptLock found
- Complies with ADR-015 Decision 1 (workflow-level concurrency instead)

Rate limiting validation: [FAIL]
- Lines 143-169: Test-RateLimitSafe only checks core and graphql resources
- ADR-015 Decision 2 requires checking 5 resources with specific thresholds
- Missing: search (15), code_scanning_autofix (5), audit_log_streaming (7), code_search (5)

### Component 4: Resolve-PRReviewThread.ps1

**Status**: [FAIL]

GraphQL injection vulnerabilities:
1. **Mutation query (lines 41-50)**:
   - Line 43: `resolveReviewThread(input: {threadId: "$Id"})`
   - String interpolation allows injection via $Id parameter
   - Should use: `mutation($threadId: ID!) { resolveReviewThread(input: {threadId: $threadId}) }`

2. **Query (lines 84-104)**:
   - Line 86: `repository(owner: "$($repo.owner.login)", name: "$($repo.name)")`
   - Line 87: `pullRequest(number: $PR)`
   - Owner/name use string interpolation (injection risk)
   - Should use variables: `query($owner: String!, $name: String!, $prNumber: Int!)`

Input validation: MISSING
- ThreadId not validated before use in mutation
- PR number not validated (int type provides partial protection)
- Owner/Repo from `gh repo view` but not revalidated

## ADR-015 Compliance Matrix

| Decision | Requirement | Status | Evidence |
|----------|-------------|--------|----------|
| Decision 1 | Workflow-level concurrency (no file locks) | [PASS] | No Enter-ScriptLock/Exit-ScriptLock in any modified files |
| Decision 2 | Multi-resource rate limiting | [FAIL] | Test-RateLimitSafe checks 2/5 required resources |
| Decision 3 | Input validation for git operations | [PARTIAL] | Branch validation complete, ThreadId validation missing |
| Decision 4 | DryRun-first deployment | N/A | Not applicable to security fixes |
| Decision 5 | BOT_PAT for attribution | N/A | Not modified in this PR |

**Overall ADR-015 Compliance**: 1/3 applicable decisions pass

## Attack Vectors Still Present

### Vector 1: GraphQL Injection via ThreadId

**Scenario**: Attacker creates PR review comment with crafted ThreadId

**Exploitation**:
```graphql
# Malicious ThreadId value:
PRRT_xxx"} thread{id} } mutation{deleteIssue(input:{issueId:"...
```

**Impact**: Arbitrary GraphQL mutations executed with bot credentials

**Likelihood**: MEDIUM (requires control of review thread creation or MitM attack)

**Mitigation Required**: Parameterize Resolve-PRReviewThread.ps1 mutations

### Vector 2: GraphQL Injection via Repository Metadata

**Scenario**: Attacker compromises `gh repo view` output or MitM attacks GitHub API

**Exploitation**:
```json
{"owner": {"login": "owner\", __typename:\"DeletedUser\"} } repository(owner:\"attacker"}}
```

**Impact**: Query arbitrary repositories or inject mutations

**Likelihood**: LOW (requires API compromise or MitM)

**Mitigation Required**: Parameterize repository query in Resolve-PRReviewThread.ps1

### Vector 3: Rate Limit Exhaustion

**Scenario**: PR maintenance workflow makes 30+ search API calls in one run

**Exploitation**: Automation triggers during high PR volume period

**Impact**: Workflow fails silently; PRs not maintained; search API locked for 60 minutes

**Likelihood**: HIGH during PR bursts (search limit: 30/hour)

**Mitigation Required**: Implement full ADR-015 Decision 2 rate limit checks

## Questions for Implementer

1. **GraphQL Injection**: Was Resolve-PRReviewThread.ps1 intentionally excluded from the GraphQL injection fixes?
   - If yes: What security boundary prevents ThreadId injection?
   - If no: Should this be included in PR #453 or separate PR?

2. **Rate Limiting**: Is the simplified rate limit check (core + graphql only) a deliberate deviation from ADR-015?
   - If yes: Should ADR-015 be updated to reflect actual implementation?
   - If no: Should full multi-resource checking be implemented per ADR specification?

3. **Input Validation**: What is the expected format for ThreadId (GraphQL global ID)?
   - Pattern: PRRT_[alphanumeric]+?
   - Length constraints?
   - Should validation reject unexpected formats?

## Recommendations

### Immediate Actions (Block Merge)

1. **Fix GraphQL injection in Resolve-PRReviewThread.ps1**:
   ```powershell
   # Line 41-50: Convert mutation to parameterized
   $mutation = @'
   mutation($threadId: ID!) {
       resolveReviewThread(input: {threadId: $threadId}) {
           thread { id isResolved }
       }
   }
   '@
   $result = gh api graphql -f query=$mutation -f threadId="$Id"

   # Line 84-104: Convert query to parameterized
   $query = @'
   query($owner: String!, $name: String!, $prNumber: Int!) {
       repository(owner: $owner, name: $name) {
           pullRequest(number: $prNumber) { ... }
       }
   }
   '@
   $result = gh api graphql -f query=$query -f owner="$($repo.owner.login)" -f name="$($repo.name)" -F prNumber=$PR
   ```

2. **Implement full rate limit validation** per ADR-015:
   ```powershell
   function Test-RateLimitSafe {
       $limits = gh api rate_limit | ConvertFrom-Json
       $thresholds = @{
           'core' = 100
           'graphql' = 50
           'search' = 15
           'code_scanning_autofix' = 5
           'audit_log_streaming' = 7
           'code_search' = 5
       }
       foreach ($resource in $thresholds.Keys) {
           if ($limits.resources.$resource.remaining -lt $thresholds[$resource]) {
               return $false
           }
       }
       return $true
   }
   ```

### Follow-up Actions (Separate PR)

3. **Add input validation for ThreadId**:
   ```powershell
   function Test-SafeThreadId {
       param([string]$ThreadId)
       # GraphQL global ID format: PRRT_[base64-like string]
       return $ThreadId -match '^PRRT_[A-Za-z0-9_-]+$'
   }
   ```

4. **Audit all GraphQL calls** in repository:
   - Search: `gh api graphql -f query=`
   - Verify: No string interpolation in query bodies
   - Convert: Any remaining injection vectors

## Approval Conditions

Before this PR can be approved:

1. [MANDATORY] Resolve-PRReviewThread.ps1 GraphQL injection vulnerabilities fixed
2. [MANDATORY] Rate limit validation implements ADR-015 Decision 2 completely
3. [RECOMMENDED] Add unit tests for GraphQL parameterization (verify no string interpolation)
4. [RECOMMENDED] Document decision if ADR-015 requirements intentionally not met

## Reversibility Assessment

All changes are reversible:
- GraphQL parameterization: Can revert to string interpolation (not recommended)
- Input validation: Can remove validation functions (security regression)
- File-based locking removal: Can re-add (violates ADR-015)

**Risk of reversal**: HIGH - reverting would reintroduce known security vulnerabilities

## Impact Analysis Review

N/A - This PR is a security fix, not a feature requiring impact analysis

## Revision History

- 2025-12-26: Initial critique - NEEDS REVISION (GraphQL injection, rate limiting)
