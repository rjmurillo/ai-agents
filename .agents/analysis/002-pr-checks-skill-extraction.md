# Analysis: Extract CI Check Verification as GitHub Skill Script

## 1. Objective and Scope

**Objective**: Evaluate feasibility of extracting `Test-PRHasFailingChecks` from `Invoke-PRMaintenance.ps1` as a standalone GitHub skill script.

**Scope**:
- Current implementation analysis (GraphQL vs REST)
- Dependencies and extraction complexity
- Comparison with bash `gh pr checks` approach
- Integration with existing GitHub skill patterns
- Relationship to issue #369 (CI verification) and PR #471

## 2. Context

PR #471 adds mandatory CI verification to pr-comment-responder using bash `gh pr checks` command. The Invoke-PRMaintenance.ps1 script already has `Test-PRHasFailingChecks` function that uses GraphQL statusCheckRollup. This creates duplication and raises questions about the ideal approach for a reusable skill script.

## 3. Approach

**Methodology**: Code analysis, API comparison, skill pattern review

**Tools Used**: Read, Grep, Bash (gh CLI testing)

**Limitations**: `gh pr checks --json` flag does not exist (discovered during testing). Documentation references are outdated.

## 4. Data and Analysis

### Evidence Gathered

| Finding | Source | Confidence |
|---------|--------|------------|
| Test-PRHasFailingChecks uses GraphQL statusCheckRollup | Invoke-PRMaintenance.ps1 L367-454 | High |
| Function has 13 Pester unit tests with 100% coverage | Invoke-PRMaintenance.Tests.ps1 L172-403 | High |
| Function is self-contained with internal Get-SafeProperty helper | Code review L386-410 | High |
| pr-comment-responder uses bash `gh pr checks` (not JSON mode) | pr-comment-responder.shared.md L1094 | High |
| `gh pr checks --json` flag does NOT exist | gh CLI testing | High |
| statusCheckRollup query embedded in Get-OpenPRs GraphQL | Invoke-PRMaintenance.ps1 L258-273 | High |
| Issue #369 describes root cause: missing CI verification | gh issue view 369 | High |
| PR #471 addresses #369 with bash approach | gh pr view 471 | High |
| Issue #97 requests review thread scripts (GraphQL required) | gh issue view 97 | Medium |
| Issue #155 proposes GraphQL vs REST capability matrix | gh issue view 155 | Medium |

### Facts (Verified)

**Current Implementation**:

```powershell
# Invoke-PRMaintenance.ps1 L367-454
function Test-PRHasFailingChecks {
    param([Parameter(Mandatory)] $PR)

    # Expects PR object from Get-OpenPRs GraphQL query containing:
    # $PR.commits.nodes[0].commit.statusCheckRollup

    # Returns: bool ($true if failures detected, $false otherwise)

    # Detection logic:
    # 1. Check rollup.state for FAILURE/ERROR
    # 2. Check individual contexts for FAILURE conclusion/state
    # 3. Handles both CheckRun (conclusion) and StatusContext (state)
}
```

**Embedded GraphQL Query (Get-OpenPRs L258-273)**:

```graphql
commits(last: 1) {
    nodes {
        commit {
            statusCheckRollup {
                state
                contexts(first: 100) {
                    nodes {
                        ... on CheckRun { name conclusion status }
                        ... on StatusContext { context state }
                    }
                }
            }
        }
    }
}
```

**Bash Approach (pr-comment-responder.md L1094)**:

```bash
# NOT VALID - gh pr checks does not support --json
gh pr checks [number] --json name,state,conclusion,detailsUrl

# ACTUAL gh pr checks syntax
gh pr checks [number]              # Human-readable output
gh pr checks [number] --required   # Only required checks
gh pr checks [number] --watch      # Poll until completion
```

**Output Format of `gh pr checks` (text, not JSON)**:

```
All checks were successful
11 successful, 0 failing, and 0 pending checks

✓  Aggregate Results                    21m56s  https://github.com/.../actions/runs/...
✓  Build and Test (macos-latest)        6m52s   https://github.com/.../actions/runs/...
✓  Build and Test (ubuntu-latest)       4m18s   https://github.com/.../actions/runs/...
```

### Hypotheses (Unverified)

- REST API `GET /repos/{owner}/{repo}/commits/{ref}/check-runs` might provide equivalent data to statusCheckRollup
- GraphQL pagination limit of 100 contexts might be insufficient for repos with many checks
- Combining REST check-runs with REST check-suites could replicate rollup logic

## 5. Results

### Extraction Feasibility: MODERATE COMPLEXITY

**Self-Contained Code**: Yes - includes Get-SafeProperty helper, no external dependencies beyond input PR object

**Input Dependency**: Requires PR object from GraphQL query with statusCheckRollup structure

**Test Coverage**: Excellent - 13 unit tests covering edge cases (nulls, PSObjects, hashtables, mixed states)

**API Choice Mismatch**:
- Invoke-PRMaintenance.ps1: GraphQL statusCheckRollup (structured data, batch query)
- pr-comment-responder.md: bash `gh pr checks` (text parsing, interactive)
- PR #471: Uses text-based approach despite documentation showing `--json` (which does not exist)

### Trade-offs: GraphQL vs Bash

| Aspect | GraphQL statusCheckRollup | Bash `gh pr checks` |
|--------|---------------------------|---------------------|
| Data Format | Structured JSON with rollup state | Text output (human-readable) |
| Batch Queries | Yes (Get-OpenPRs fetches 20 PRs with checks) | No (one PR per invocation) |
| Parsing Complexity | Simple (already JSON) | High (text parsing, fragile) |
| Reusability | Requires PR object from GraphQL | Standalone (just needs PR number) |
| Watch/Poll | Manual implementation | Built-in (`--watch` flag) |
| Required Checks Filter | Manual (check metadata) | Built-in (`--required` flag) |
| Detail URL Access | Yes (contexts[].detailsUrl) | Visible in text output |
| Exit Code on Failure | No (returns data, you decide) | Yes (--fail-fast) |

### Comparison: REST API Alternative

GitHub REST API endpoint: `GET /repos/{owner}/{repo}/commits/{ref}/check-runs`

**Advantages**:
- Can fetch checks for specific commit SHA
- Returns JSON (no text parsing)
- Works standalone (no GraphQL query dependency)

**Disadvantages**:
- No rollup state (must aggregate manually)
- Pagination required (30 per page default)
- Separate call per PR (no batching)
- More API calls (2-3x vs GraphQL batch)

## 6. Discussion

### Core Problem: Documentation vs Reality

The pr-comment-responder.md documentation (and PR #471) references `gh pr checks --json` syntax that does NOT exist. The actual `gh pr checks` command outputs human-readable text. This means:

1. Current bash approach requires text parsing (fragile, error-prone)
2. GraphQL approach provides structured data (robust, testable)
3. REST API approach is middle ground (structured, but not batched)

### Skill Script Design Considerations

**Option A: PowerShell wrapper for `gh pr checks` (text parsing)**

```powershell
# Get-PRChecks.ps1 - wraps gh pr checks text output
param([int]$PullRequest)
$output = gh pr checks $PullRequest 2>&1
# Parse text: "✓  Check Name  5m23s  https://..."
# Return: PSObject with Name, Status, Duration, Url
```

**Pros**: Matches bash documentation style, uses `gh` CLI features (--watch, --required)

**Cons**: Fragile text parsing, no batch support, loses structured data

**Option B: GraphQL standalone script (fetch statusCheckRollup)**

```powershell
# Get-PRChecks.ps1 - GraphQL query for specific PR
param([int]$PullRequest)
$query = @'
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      commits(last: 1) {
        nodes {
          commit {
            statusCheckRollup {
              state
              contexts(first: 100) {
                nodes {
                  ... on CheckRun { name conclusion status detailsUrl }
                  ... on StatusContext { context state targetUrl }
                }
              }
            }
          }
        }
      }
    }
  }
}
'@
# Execute via gh api graphql
# Return: Structured check data
```

**Pros**: Structured data, testable, reuses Invoke-PRMaintenance patterns

**Cons**: Requires GraphQL knowledge, no direct watch/filter support

**Option C: REST API script (fetch check-runs)**

```powershell
# Get-PRChecks.ps1 - REST API for commit checks
param([int]$PullRequest)
# 1. Get PR head SHA via gh pr view
# 2. Fetch check-runs via gh api /repos/{owner}/{repo}/commits/{sha}/check-runs
# 3. Aggregate state (all success/skipped = pass, any failure = fail)
# Return: Check list with conclusion
```

**Pros**: Structured JSON, familiar REST patterns, no GraphQL dependency

**Cons**: Multiple API calls, manual rollup logic, pagination complexity

### Recommended Approach: Option B (GraphQL)

**Rationale**:
1. **Consistency with codebase**: Invoke-PRMaintenance.ps1 already uses GraphQL statusCheckRollup
2. **Testability**: 13 existing unit tests for Test-PRHasFailingChecks logic
3. **Batch efficiency**: GraphQL enables Get-OpenPRs to fetch 20 PRs with checks in one call
4. **Structured data**: No fragile text parsing
5. **Reusability**: Extract Test-PRHasFailingChecks logic + add GraphQL query wrapper

### Impact on Issue #369 and PR #471

**Issue #369**: Correctly identifies that CI verification was missing. Root cause was not API choice but missing verification step.

**PR #471**: Addresses #369 by adding bash `gh pr checks` to pr-comment-responder. This works but:
- Documentation shows non-existent `--json` flag
- Actual implementation must parse text output (fragile)
- Creating Get-PRChecks.ps1 could replace bash approach with robust GraphQL version

## 7. Recommendations

| Priority | Recommendation | Rationale | Effort |
|----------|----------------|-----------|--------|
| P0 | Fix PR #471 documentation to remove `--json` references | Documentation shows non-existent flag | Low |
| P1 | Create `Get-PRChecks.ps1` using GraphQL approach | Provides structured data, reuses tested logic | Medium |
| P1 | Extract `Test-PRHasFailingChecks` logic as helper function | Enable reuse across Get-PRChecks.ps1 and Invoke-PRMaintenance.ps1 | Low |
| P2 | Create `Test-PRChecks.ps1` wrapper around Get-PRChecks.ps1 | Provides boolean check (mirrors Test-PRHasFailingChecks API) | Low |
| P3 | Add GraphQL vs REST capability matrix (Issue #155) | Helps developers choose correct API | Medium |

## 8. Conclusion

**Verdict**: Proceed with extraction

**Confidence**: High

**Rationale**: Test-PRHasFailingChecks is well-tested, self-contained logic that can be extracted as a GitHub skill script. GraphQL approach is superior to bash text parsing for structured data and batch queries. This addresses Issue #369 more robustly than PR #471's bash approach.

### User Impact

**What changes for you**:
- New `Get-PRChecks.ps1` script provides CI check status as structured data
- pr-comment-responder can use PowerShell script instead of bash text parsing
- Invoke-PRMaintenance.ps1 can reuse extracted helper instead of duplicating logic

**Effort required**:
- 2-3 hours to extract, test, and document
- Low risk (logic already tested with 13 unit tests)

**Risk if ignored**:
- Duplication between Invoke-PRMaintenance.ps1 and pr-comment-responder bash
- Fragile text parsing in bash approach (PR #471)
- Missed opportunity for reusable skill

## 9. Appendices

### Proposed Script Signature

**Script Name**: `Get-PRChecks.ps1`

**Location**: `.claude/skills/github/scripts/pr/`

**Parameters**:

```powershell
param(
    [Parameter(Mandatory)]
    [int]$PullRequest,

    [string]$Owner,  # Auto-infer from git remote

    [string]$Repo,   # Auto-infer from git remote

    [switch]$FailingOnly  # Filter to only failing/error checks
)
```

**Output Schema**:

```json
{
  "pullRequest": 471,
  "overallState": "SUCCESS",  // FAILURE, ERROR, PENDING, SUCCESS, EXPECTED
  "checks": [
    {
      "type": "CheckRun",
      "name": "Build and Test",
      "conclusion": "SUCCESS",
      "status": "COMPLETED",
      "detailsUrl": "https://github.com/.../runs/..."
    },
    {
      "type": "StatusContext",
      "name": "ci/circleci",
      "state": "SUCCESS",
      "targetUrl": "https://circleci.com/..."
    }
  ],
  "summary": {
    "total": 11,
    "success": 10,
    "failure": 0,
    "error": 0,
    "pending": 1,
    "skipped": 0
  }
}
```

**Exit Codes**:
- 0: Success (check data retrieved)
- 1: Invalid parameters
- 2: PR not found
- 3: API error
- 4: Authentication error

### Helper Function Extraction

**New Module**: `GitHubHelpers.psm1` (or add to existing module)

**Function**:

```powershell
function Test-PRHasFailingChecks {
    param([Parameter(Mandatory)] $StatusCheckRollup)
    # Extracted logic from Invoke-PRMaintenance.ps1 L367-454
    # Returns: bool
}
```

### Sources Consulted

- `scripts/Invoke-PRMaintenance.ps1` (L367-454, L225-297)
- `scripts/tests/Invoke-PRMaintenance.Tests.ps1` (L172-403)
- `templates/agents/pr-comment-responder.shared.md` (L1094)
- Issue #369: https://github.com/rjmurillo/ai-agents/issues/369
- Issue #97: https://github.com/rjmurillo/ai-agents/issues/97
- Issue #155: https://github.com/rjmurillo/ai-agents/issues/155
- PR #471: https://github.com/rjmurillo/ai-agents/pull/471
- GitHub GraphQL API: https://docs.github.com/en/graphql/reference/objects#statuscheckrollup
- `gh pr checks` CLI documentation: `gh pr checks --help`

### Data Transparency

**Found**:
- Complete Test-PRHasFailingChecks implementation with 13 unit tests
- GraphQL statusCheckRollup query structure
- pr-comment-responder bash approach (text-based)
- Confirmation that `gh pr checks --json` does NOT exist

**Not Found**:
- Existing Get-PRChecks.ps1 script in GitHub skill
- REST API check-runs pagination handling examples
- Documentation explaining why bash was chosen over GraphQL for PR #471
