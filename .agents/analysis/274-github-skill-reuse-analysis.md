# Analysis: GitHub Skill PowerShell Reuse Opportunities

## 1. Objective and Scope

**Objective**: Identify duplicated code patterns across GitHub skill scripts and recommend consolidation opportunities in GitHubHelpers.psm1.

**Scope**: All 24 PowerShell scripts in `.claude/skills/github/scripts/` directories:
- Issue operations (8 scripts)
- PR operations (15 scripts)
- Reactions (1 script)

## 2. Context

Issue #274 requests analysis of code reuse opportunities following the DRY principle. The repository already has a `GitHubHelpers.psm1` module with shared functions, but scripts still contain duplicated patterns that should be extracted.

**Current module coverage** (1021 lines):
- Input validation (CWE-78, CWE-22 prevention)
- Repository inference and resolution
- Authentication checks
- Error handling with context awareness
- API pagination
- Issue comment operations
- Trusted source filtering
- Bot configuration management
- Rate limit checking
- Formatting helpers (emoji mapping)

## 3. Approach

**Methodology**:
1. Read all 24 skill scripts
2. Catalog common patterns across scripts
3. Compare with existing GitHubHelpers.psm1 functions
4. Identify gaps and duplication
5. Recommend refactoring based on frequency and complexity

**Tools Used**:
- Read tool for script analysis
- Pattern recognition across scripts
- Comparison with existing module

**Limitations**:
- Did not execute scripts for runtime behavior analysis
- Analysis based on static code review only
- Did not analyze `.github/workflows/` YAML files (out of scope)

## 4. Data and Analysis

### Evidence Gathered

| Finding | Source | Confidence |
|---------|--------|------------|
| Repository inference duplicated in 1 script | Get-UnresolvedReviewThreads.ps1 | High |
| Body file reading pattern duplicated in 4 scripts | New-Issue, New-PR, Post-PRCommentReply, Post-IssueComment | High |
| Conditional execution based on `$env:GITHUB_OUTPUT` in 3 scripts | New-Issue, Post-IssueComment, New-PR | High |
| Marker-based idempotency logic duplicated | Post-IssueComment has full implementation | Medium |
| GraphQL query execution pattern | Get-UnresolvedReviewThreads.ps1 | High |
| Comment type routing (review vs issue) | Post-PRCommentReply, Get-PRReviewComments | High |
| Conventional commit validation | New-PR.ps1 only | High |
| PR validation orchestration | New-PR.ps1 only | High |
| Audit logging pattern | New-PR.ps1 only | High |
| Batch operation pattern | Add-CommentReaction.ps1 | High |

### Facts (Verified)

**Pattern 1: Repository Info Inference**
- **Current state**: `Get-RepoInfo` exists in GitHubHelpers.psm1 (lines 183-210)
- **Duplication**: Get-UnresolvedReviewThreads.ps1 (lines 60-76) reimplements this
- **Impact**: 17 lines of duplicated code
- **Evidence**: Identical regex pattern `github\.com[:/]([^/]+)/([^/.]+)`

**Pattern 2: Body File Reading**
- **Scripts affected**: New-Issue.ps1, New-PR.ps1, Post-PRCommentReply.ps1, Post-IssueComment.ps1
- **Pattern**:
  ```powershell
  if ($BodyFile) {
      if (-not (Test-Path $BodyFile)) { Write-ErrorAndExit "Body file not found: $BodyFile" 2 }
      $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8
  }
  ```
- **Current state**: No helper exists for this
- **Recommendation**: Extract to `Get-BodyContent` function
- **Lines duplicated**: 12 lines across 4 scripts = 48 total

**Pattern 3: GitHub Actions Output Writing**
- **Scripts affected**: New-Issue.ps1, Post-IssueComment.ps1
- **Pattern**:
  ```powershell
  if ($env:GITHUB_OUTPUT) {
      Add-Content -Path $env:GITHUB_OUTPUT -Value "success=true"
      Add-Content -Path $env:GITHUB_OUTPUT -Value "issue=$Issue"
      # ... more outputs
  }
  ```
- **Current state**: No helper exists
- **Recommendation**: Extract to `Write-GitHubOutput` function
- **Lines duplicated**: 15-30 lines per script (varies by output count)

**Pattern 4: Marker-Based Idempotency**
- **Scripts affected**: Post-IssueComment.ps1 (full implementation)
- **Pattern**: Check for HTML comment marker, update existing comment or skip
- **Lines**: 66 lines (lines 69-134)
- **Current state**: No helper exists
- **Recommendation**: Extract to `Invoke-IdempotentComment` function
- **Reuse potential**: Other comment posting scenarios (PR comments, workflow updates)

**Pattern 5: GraphQL Query Execution**
- **Scripts affected**: Get-UnresolvedReviewThreads.ps1
- **Pattern**:
  ```powershell
  $query = @'
  query(...) { ... }
  '@
  $result = gh api graphql -f query=$query -f owner="$Owner" -f name="$Repo" ...
  ```
- **Current state**: No GraphQL helper exists
- **Recommendation**: Extract to `Invoke-GhGraphQL` function
- **Benefit**: Consistent error handling, variable binding, pagination support

**Pattern 6: Comment Type Routing**
- **Scripts affected**: Post-PRCommentReply.ps1, Get-PRReviewComments.ps1, Add-CommentReaction.ps1
- **Pattern**: Switch between review comments and issue comments endpoints
- **Current state**: Inline switch statements in each script
- **Recommendation**: Extract to `Get-CommentEndpoint` function

**Pattern 7: Conventional Commit Validation**
- **Scripts affected**: New-PR.ps1 only (lines 73-89)
- **Pattern**: Regex validation for conventional commit format
- **Current state**: Inline in New-PR.ps1
- **Recommendation**: Extract to `Test-ConventionalCommit` function
- **Reuse potential**: Commit validation, issue title validation, changelog generation

**Pattern 8: Validation Orchestration**
- **Scripts affected**: New-PR.ps1 only (lines 91-145)
- **Pattern**: Run multiple validation scripts in sequence with progress output
- **Current state**: Inline in New-PR.ps1
- **Recommendation**: Extract to `Invoke-ValidationPipeline` function
- **Benefit**: Reusable for other pre-operation validation scenarios

**Pattern 9: Audit Logging**
- **Scripts affected**: New-PR.ps1 only (lines 147-180)
- **Pattern**: Write audit trail to `.agents/audit/` with timestamp, user, reason
- **Current state**: Inline in New-PR.ps1
- **Recommendation**: Extract to `Write-AuditEntry` function
- **Reuse potential**: Other operations requiring audit trail (merge, label changes)

**Pattern 10: Batch Operations**
- **Scripts affected**: Add-CommentReaction.ps1
- **Pattern**: Process array of IDs in loop with success/failure tracking
- **Current state**: Inline implementation
- **Recommendation**: Extract to `Invoke-BatchOperation` generic helper
- **Benefit**: Consistent batch processing for other operations (labels, assignees)

### Hypotheses (Unverified)

- **Hypothesis 1**: Other workflows may benefit from idempotent comment posting
- **Hypothesis 2**: GraphQL pagination may be needed for repositories with 100+ review threads
- **Hypothesis 3**: Batch operation pattern could apply to label management, assignee updates

## 5. Results

**Duplication Quantified**:
- **Pattern 1**: 17 lines (1 script) - ALREADY EXISTS in module, just not used
- **Pattern 2**: 48 lines (4 scripts)
- **Pattern 3**: 60-120 lines estimated (3 scripts, varies)
- **Pattern 4**: 66 lines (1 script, high complexity)
- **Pattern 5**: 30 lines estimated (1 script)
- **Pattern 6**: 20 lines estimated (3 scripts)
- **Pattern 7**: 17 lines (1 script)
- **Pattern 8**: 55 lines (1 script)
- **Pattern 9**: 34 lines (1 script)
- **Pattern 10**: 40 lines (1 script)

**Total duplicated/extractable lines**: ~387-447 lines across 24 scripts

**Scripts NOT using existing module functions**:
1. Get-UnresolvedReviewThreads.ps1 - should use `Get-RepoInfo`, `Assert-GhAuthenticated`
2. New-PR.ps1 - does NOT import GitHubHelpers.psm1 (relies on inline helpers)

**Scripts correctly using module**:
- 21 out of 24 scripts import and use GitHubHelpers.psm1
- All use `Assert-GhAuthenticated`, `Resolve-RepoParams`, `Write-ErrorAndExit`

## 6. Discussion

### Why Duplication Exists

1. **New-PR.ps1 independence**: Script predates current module structure, uses inline helpers for self-containment
2. **Get-UnresolvedReviewThreads.ps1**: Recent addition, didn't follow module import pattern
3. **Pattern evolution**: Body file reading, GitHub Actions outputs emerged organically across scripts
4. **Idempotency complexity**: Only Post-IssueComment.ps1 needed it initially, so extraction was deferred

### Impact of Current State

**Maintenance burden**:
- Bug fixes require changing 4 scripts for body file reading
- GitHub Actions output format changes affect 3 scripts
- Repository inference logic duplicated despite module function existing

**Inconsistency risk**:
- Error messages differ across scripts ("Body file not found" vs "File not found")
- Error codes may diverge (exit 2 vs exit 1 for file not found)
- Validation logic may have subtle differences

**Testing overhead**:
- Each duplicated pattern requires separate test coverage
- Integration tests must verify consistency across scripts

### Benefits of Consolidation

**Quantified benefits**:
- Reduce codebase by 387-447 lines
- Consolidate 10 patterns into module functions
- Single source of truth for error messages and exit codes
- Simplified testing (test module functions once, not per-script)

**Quality improvements**:
- Consistent error handling across all scripts
- Easier to add features (e.g., GraphQL pagination)
- Clearer separation of concerns

## 7. Recommendations

| Priority | Recommendation | Rationale | Effort |
|----------|----------------|-----------|--------|
| P0 | Fix Get-UnresolvedReviewThreads.ps1 to use GitHubHelpers.psm1 | Module functions exist, just not imported | 15 min |
| P0 | Fix New-PR.ps1 to import GitHubHelpers.psm1 | Critical path script, should follow module pattern | 30 min |
| P1 | Extract `Get-BodyContent` for file/inline body resolution | Used in 4 scripts, simple extraction | 1 hour |
| P1 | Extract `Write-GitHubOutput` for Actions output | Used in 3 scripts, improves CI/CD consistency | 1 hour |
| P1 | Extract `Get-CommentEndpoint` for review/issue routing | Used in 3 scripts, prevents endpoint errors | 1 hour |
| P2 | Extract `Invoke-IdempotentComment` for marker-based updates | Complex but high-value for CI/CD workflows | 3 hours |
| P2 | Extract `Test-ConventionalCommit` validation | Future-proof for commit/issue validation | 1 hour |
| P2 | Extract `Invoke-GhGraphQL` helper | Enables consistent GraphQL usage, pagination | 2 hours |
| P3 | Extract `Invoke-ValidationPipeline` orchestrator | Low reuse currently, but valuable pattern | 2 hours |
| P3 | Extract `Write-AuditEntry` helper | Low reuse currently, defer until needed | 1 hour |
| P3 | Extract `Invoke-BatchOperation` generic helper | Interesting abstraction, but Add-CommentReaction works well as-is | 3 hours |

**Total estimated effort**: 15.5 hours (P0-P2: 10.5 hours, P3: 5 hours)

### Implementation Sequence

**Phase 1: Quick Wins (P0, 45 min)**
1. Update Get-UnresolvedReviewThreads.ps1 to import GitHubHelpers.psm1
2. Update New-PR.ps1 to import GitHubHelpers.psm1
3. Test both scripts for regression

**Phase 2: High-Frequency Patterns (P1, 3 hours)**
1. Add `Get-BodyContent` to GitHubHelpers.psm1
2. Add `Write-GitHubOutput` to GitHubHelpers.psm1
3. Add `Get-CommentEndpoint` to GitHubHelpers.psm1
4. Update 4 scripts using body file pattern
5. Update 3 scripts using GitHub Actions output
6. Update 3 scripts using comment endpoint routing
7. Test all affected scripts

**Phase 3: High-Complexity Patterns (P2, 7 hours)**
1. Add `Invoke-IdempotentComment` to GitHubHelpers.psm1
2. Add `Test-ConventionalCommit` to GitHubHelpers.psm1
3. Add `Invoke-GhGraphQL` to GitHubHelpers.psm1
4. Refactor Post-IssueComment.ps1 to use idempotent helper
5. Refactor New-PR.ps1 to use conventional commit helper
6. Refactor Get-UnresolvedReviewThreads.ps1 to use GraphQL helper
7. Test all affected scripts

**Phase 4: Deferred (P3, as needed)**
- Extract validation pipeline, audit logging, batch operations when second use case emerges

## 8. Conclusion

**Verdict**: Proceed with phased refactoring

**Confidence**: High

**Rationale**: Analysis identified 10 clear duplication patterns across 24 scripts. Module already has strong foundation (1021 lines), but 387-447 lines of code are duplicated or could be shared. Quick wins (P0) provide immediate value with minimal risk. P1-P2 patterns affect multiple scripts and improve consistency. P3 patterns are single-use currently and should wait for second use case.

### User Impact

**What changes for you**:
- More consistent error messages across GitHub skills
- Easier to add new GitHub operations (reuse helpers)
- Reduced risk of bugs from duplicated logic

**Effort required**:
- Phase 1: 45 minutes (immediate fixes)
- Phase 2: 3 hours (high-frequency patterns)
- Phase 3: 7 hours (complex patterns)
- Total: 10.75 hours for P0-P2

**Risk if ignored**:
- Maintenance burden increases as new scripts are added
- Inconsistent behavior across scripts (error codes, messages)
- Bug fixes require updates to multiple scripts
- Testing overhead grows linearly with duplication

## 9. Appendices

### Sources Consulted

- `.claude/skills/github/modules/GitHubHelpers.psm1` (1021 lines)
- All 24 scripts in `.claude/skills/github/scripts/`:
  - `issue/Get-IssueContext.ps1`
  - `issue/Get-PriorityIssues.ps1`
  - `issue/Invoke-CopilotAssignment.ps1`
  - `issue/New-Issue.ps1`
  - `issue/Post-IssueComment.ps1`
  - `issue/Set-IssueAssignee.ps1`
  - `issue/Set-IssueLabels.ps1`
  - `issue/Set-IssueMilestone.ps1`
  - `pr/Close-PR.ps1`
  - `pr/Detect-CopilotFollowUpPR.ps1`
  - `pr/Get-PRChecks.ps1`
  - `pr/Get-PRContext.ps1`
  - `pr/Get-PRReviewComments.ps1`
  - `pr/Get-PRReviewers.ps1`
  - `pr/Get-PRReviewThreads.ps1`
  - `pr/Get-UnaddressedComments.ps1`
  - `pr/Get-UnresolvedReviewThreads.ps1`
  - `pr/Invoke-PRCommentProcessing.ps1`
  - `pr/Merge-PR.ps1`
  - `pr/New-PR.ps1`
  - `pr/Post-PRCommentReply.ps1`
  - `pr/Resolve-PRReviewThread.ps1`
  - `pr/Test-PRMerged.ps1`
  - `reactions/Add-CommentReaction.ps1`

### Data Transparency

**Found**:
- 10 distinct duplication patterns
- 2 scripts NOT using existing module functions
- 21 scripts correctly using module
- Existing module has 21 exported functions
- Module provides comprehensive foundation (validation, auth, repo, error handling, API helpers)

**Not Found**:
- No evidence of duplication in workflow YAML files (out of scope)
- No runtime performance data (static analysis only)
- No evidence of bugs caused by current duplication
- No user complaints about inconsistent behavior

### Proposed Function Signatures

```powershell
# Pattern 2: Body file reading
function Get-BodyContent {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(ParameterSetName='Inline', Mandatory)]
        [string]$Body,

        [Parameter(ParameterSetName='File', Mandatory)]
        [string]$BodyFile,

        [string]$AllowedBase  # Optional path validation
    )
    # Returns body content from inline or file
    # Validates file exists and safe path
    # Exit code 2 on file not found
}

# Pattern 3: GitHub Actions outputs
function Write-GitHubOutput {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [hashtable]$Values  # @{ success = $true; issue = 123 }
    )
    # Writes to $env:GITHUB_OUTPUT if set
    # Silently skips if not in Actions context
    # Handles key=value formatting
}

# Pattern 5: GraphQL queries
function Invoke-GhGraphQL {
    [CmdletBinding()]
    [OutputType([PSCustomObject])]
    param(
        [Parameter(Mandatory)]
        [string]$Query,

        [hashtable]$Variables = @{},

        [switch]$Paginate  # Future: handle pagination cursor
    )
    # Executes GraphQL query with variables
    # Returns parsed JSON result
    # Exit code 3 on API error
}

# Pattern 6: Comment endpoint routing
function Get-CommentEndpoint {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,

        [Parameter(Mandatory)]
        [string]$Repo,

        [Parameter(Mandatory)]
        [int]$Number,  # PR or issue number

        [Parameter(Mandatory)]
        [ValidateSet('Review', 'Issue', 'ReviewReaction', 'IssueReaction')]
        [string]$Type,

        [long]$CommentId  # For specific comment operations
    )
    # Returns correct API endpoint for comment operation
    # Example: repos/owner/repo/pulls/comments/123/reactions
}

# Pattern 4: Idempotent comments
function Invoke-IdempotentComment {
    [CmdletBinding()]
    [OutputType([PSCustomObject])]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,

        [Parameter(Mandatory)]
        [string]$Repo,

        [Parameter(Mandatory)]
        [int]$Issue,

        [Parameter(Mandatory)]
        [string]$Body,

        [Parameter(Mandatory)]
        [string]$Marker,  # HTML comment marker

        [switch]$UpdateIfExists  # Upsert vs write-once
    )
    # Posts or updates comment based on marker
    # Returns: @{ Success; CommentId; Updated; Skipped }
    # Exit code 0 on success or idempotent skip
}

# Pattern 7: Conventional commit validation
function Test-ConventionalCommit {
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory)]
        [string]$Message
    )
    # Returns $true if message matches conventional commit format
    # Supports: feat, fix, docs, style, refactor, perf, test, chore, ci, build, revert
    # Scope optional, breaking change (!) optional
}
```
