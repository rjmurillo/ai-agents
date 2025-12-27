# Implementation Prompts: Acknowledged vs Resolved Fix

## Source

- Task List: `.agents/planning/tasks-acknowledged-vs-resolved.md`
- PRD: `.agents/planning/PRD-acknowledged-vs-resolved.md`

---

## TASK-001: Implement GraphQL thread resolution query

### Prompt for Implementer

```
Implement a GraphQL query to retrieve review thread resolution status for a pull request.

CONTEXT:
- File: scripts/Invoke-PRMaintenance.ps1
- Location: Add after existing GraphQL queries (search for "gh api graphql" patterns)
- Reference pattern: .claude/skills/github/scripts/pr/Resolve-PRReviewThread.ps1 (lines 35-60)

REQUIREMENTS:
1. Query structure must match FR1 specification:
   ```graphql
   query {
       repository(owner: "$Owner", name: "$Repo") {
           pullRequest(number: $PR) {
               reviewThreads(first: 100) {
                   nodes {
                       id
                       isResolved
                       comments(first: 1) {
                           nodes { databaseId }
                       }
                   }
               }
           }
       }
   }
   ```

2. Query must accept Owner, Repo, and PR number as parameters
3. Query must use POST /graphql endpoint via `gh api graphql`
4. Query must handle API failure gracefully (return error info)

ACCEPTANCE CRITERIA (all must be checked):
- [ ] Query uses GraphQL API endpoint POST /graphql
- [ ] Query structure matches FR1 specification
- [ ] Query retrieves first 100 threads with id, isResolved, and first comment databaseId
- [ ] Query accepts Owner, Repo, and PR number as parameters
- [ ] Query handles API failure gracefully (returns error info)

DO NOT:
- Modify existing GraphQL queries
- Add unit tests (TASK-003 handles this)
- Integrate with main workflow (TASK-006 handles this)
```

---

## TASK-002: Implement Get-UnresolvedReviewThreads function

### Prompt for Implementer

```
Implement the Get-UnresolvedReviewThreads function to detect unresolved review threads.

CONTEXT:
- File: scripts/Invoke-PRMaintenance.ps1
- Location: Add after line ~500 (after existing helper functions)
- Depends on: TASK-001 GraphQL query

FUNCTION SIGNATURE (FR2):
```powershell
function Get-UnresolvedReviewThreads {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,

        [Parameter(Mandatory)]
        [string]$Repo,

        [Parameter(Mandatory)]
        [int]$PR
    )
    # Returns: Array of thread objects where isResolved = false
}
```

BEHAVIOR REQUIREMENTS:
1. Execute GraphQL query from TASK-001
2. Filter results to threads where `isResolved = false`
3. Return empty array when all threads are resolved
4. Return empty array on API failure (log warning via Write-Log)
5. Follow Skill-PowerShell-002: Always return array type, never $null

PATTERN TO FOLLOW:
```powershell
# From Resolve-PRReviewThread.ps1
$query = @"
query {
    repository(owner: "$Owner", name: "$Repo") {
        pullRequest(number: $PRNumber) {
            reviewThreads(first: 100) {
                nodes { id isResolved comments(first: 1) { nodes { databaseId } } }
            }
        }
    }
}
"@

$result = gh api graphql -f query="$query" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Log "GraphQL API failed: $result" -Level WARN
    return @()
}

$threads = ($result | ConvertFrom-Json).data.repository.pullRequest.reviewThreads.nodes
return @($threads | Where-Object { -not $_.isResolved })
```

ACCEPTANCE CRITERIA:
- [ ] Function signature matches FR2 specification
- [ ] Function returns array of thread objects where isResolved = false
- [ ] Function returns empty array when all threads are resolved
- [ ] Function returns empty array on API failure with logged warning
- [ ] Function follows Skill-PowerShell-002 (always returns array, never $null)
- [ ] Function includes CmdletBinding and proper parameter attributes

DO NOT:
- Add unit tests (TASK-003 handles this)
- Integrate with Get-UnaddressedComments (TASK-004 handles this)
```

---

## TASK-003: Write unit tests for Get-UnresolvedReviewThreads

### Prompt for Implementer

```
Create Pester tests for Get-UnresolvedReviewThreads function.

CONTEXT:
- File: scripts/tests/Invoke-PRMaintenance.Tests.ps1
- Location: Add new Describe block for "Get-UnresolvedReviewThreads"
- Depends on: TASK-002 function implementation

TEST CASES REQUIRED:

1. All threads resolved returns empty array
   ```powershell
   Mock gh { return '{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[{"id":"T1","isResolved":true}]}}}}}' }
   $result = Get-UnresolvedReviewThreads -Owner "test" -Repo "repo" -PR 123
   $result.Count | Should -Be 0
   ```

2. Some threads unresolved returns correct count
   ```powershell
   Mock gh { return '{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[{"id":"T1","isResolved":true},{"id":"T2","isResolved":false}]}}}}}' }
   $result = Get-UnresolvedReviewThreads -Owner "test" -Repo "repo" -PR 123
   $result.Count | Should -Be 1
   $result[0].id | Should -Be "T2"
   ```

3. No threads exist returns empty array
   ```powershell
   Mock gh { return '{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[]}}}}}' }
   $result = Get-UnresolvedReviewThreads -Owner "test" -Repo "repo" -PR 123
   $result.Count | Should -Be 0
   ```

4. GraphQL API failure returns empty array with warning
   ```powershell
   Mock gh { throw "API Error" }
   Mock Write-Log {}
   $result = Get-UnresolvedReviewThreads -Owner "test" -Repo "repo" -PR 123
   $result.Count | Should -Be 0
   Should -Invoke Write-Log -ParameterFilter { $Level -eq 'WARN' }
   ```

5. Parameters are validated correctly
   ```powershell
   { Get-UnresolvedReviewThreads -Owner "" -Repo "repo" -PR 123 } | Should -Throw
   ```

ACCEPTANCE CRITERIA:
- [ ] Test case: All threads resolved returns empty array
- [ ] Test case: Some threads unresolved returns correct count
- [ ] Test case: No threads exist returns empty array
- [ ] Test case: GraphQL API failure returns empty array with warning
- [ ] Test case: Parameters are validated correctly
- [ ] All tests pass with green status

RUN VALIDATION:
```bash
pwsh -Command "Invoke-Pester -Path scripts/tests/Invoke-PRMaintenance.Tests.ps1 -TagFilter 'Get-UnresolvedReviewThreads' -PassThru"
```
```

---

## TASK-004: Implement Get-UnaddressedComments function

### Prompt for Implementer

```
Implement the Get-UnaddressedComments function to detect comments that are unacknowledged OR unresolved.

CONTEXT:
- File: scripts/Invoke-PRMaintenance.ps1
- Location: Add after Get-UnresolvedReviewThreads function
- Depends on: TASK-002 Get-UnresolvedReviewThreads

FUNCTION SIGNATURE (FR3):
```powershell
function Get-UnaddressedComments {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,

        [Parameter(Mandatory)]
        [string]$Repo,

        [Parameter(Mandatory)]
        [int]$PRNumber,

        [Parameter()]
        [array]$Comments = $null
    )
    # Returns: Array of comments that are either unacknowledged OR unresolved
}
```

LOGIC (from PRD):
1. Fetch comments via Get-PRComments if not provided
2. Query unresolved threads via Get-UnresolvedReviewThreads
3. Extract comment IDs from unresolved threads (nodes.comments.nodes[0].databaseId)
4. Filter comments where:
   - user.type = 'Bot' AND
   - (reactions.eyes = 0 OR id in unresolvedCommentIds)
5. Return filtered array (empty if none match)

SEMANTIC MODEL (from PRD):
```
Comment Lifecycle:
[NEW] -> [ACKNOWLEDGED] -> [REPLIED] -> [RESOLVED]

Get-UnacknowledgedComments: Detects [NEW] only (reactions.eyes = 0)
Get-UnaddressedComments:    Detects [NEW], [ACKNOWLEDGED], [REPLIED] (unresolved)
```

IMPLEMENTATION PATTERN:
```powershell
function Get-UnaddressedComments {
    [CmdletBinding()]
    param(...)

    # Get comments if not provided
    if (-not $Comments) {
        $Comments = Get-PRComments -Owner $Owner -Repo $Repo -PRNumber $PRNumber
    }

    # Get unresolved thread comment IDs
    $unresolvedThreads = Get-UnresolvedReviewThreads -Owner $Owner -Repo $Repo -PR $PRNumber
    $unresolvedCommentIds = @($unresolvedThreads | ForEach-Object {
        $_.comments.nodes[0].databaseId
    } | Where-Object { $_ })

    # Filter: Bot comments that are unacknowledged OR in unresolved threads
    $unaddressed = @($Comments | Where-Object {
        $_.user.type -eq 'Bot' -and (
            $_.reactions.eyes -eq 0 -or
            $_.id -in $unresolvedCommentIds
        )
    })

    return $unaddressed
}
```

ACCEPTANCE CRITERIA:
- [ ] Function signature matches FR3 specification
- [ ] Function accepts optional Comments array parameter
- [ ] Function calls Get-PRComments if Comments not provided
- [ ] Function calls Get-UnresolvedReviewThreads to get unresolved thread IDs
- [ ] Function filters comments where user.type = 'Bot' AND (reactions.eyes = 0 OR id in unresolvedCommentIds)
- [ ] Function returns empty array when all comments are addressed
- [ ] Comment with eyes > 0 AND isResolved = true is NOT returned
- [ ] Comment with eyes = 0 OR isResolved = false IS returned

DO NOT:
- Modify Get-UnacknowledgedComments (preserve backward compatibility)
- Add unit tests (TASK-005 handles this)
```

---

## TASK-005: Write unit tests for Get-UnaddressedComments

### Prompt for Implementer

```
Create comprehensive Pester tests for Get-UnaddressedComments covering all state combinations.

CONTEXT:
- File: scripts/tests/Invoke-PRMaintenance.Tests.ps1
- Location: Add new Describe block for "Get-UnaddressedComments"
- PRD Test Fixtures: Use fixtures from PRD Appendix

TEST FIXTURES (from PRD):

Fixture 1 - PR #365 Equivalent (Acknowledged but unresolved):
```powershell
$Fixture1_Comments = @(
    @{id = 1; user = @{type = 'Bot'}; reactions = @{eyes = 1}},
    @{id = 2; user = @{type = 'Bot'}; reactions = @{eyes = 1}},
    @{id = 3; user = @{type = 'Bot'}; reactions = @{eyes = 1}},
    @{id = 4; user = @{type = 'Bot'}; reactions = @{eyes = 1}},
    @{id = 5; user = @{type = 'Bot'}; reactions = @{eyes = 1}}
)
$Fixture1_Threads = @(
    @{id = 'T1'; isResolved = $false; comments = @{nodes = @(@{databaseId = 1})}},
    @{id = 'T2'; isResolved = $false; comments = @{nodes = @(@{databaseId = 2})}},
    @{id = 'T3'; isResolved = $false; comments = @{nodes = @(@{databaseId = 3})}},
    @{id = 'T4'; isResolved = $false; comments = @{nodes = @(@{databaseId = 4})}},
    @{id = 'T5'; isResolved = $false; comments = @{nodes = @(@{databaseId = 5})}}
)
# Expected: count = 5 (all acknowledged but unresolved)
```

Fixture 2 - Fully Resolved PR:
```powershell
$Fixture2_Comments = @(
    @{id = 1; user = @{type = 'Bot'}; reactions = @{eyes = 1}},
    @{id = 2; user = @{type = 'Bot'}; reactions = @{eyes = 1}}
)
$Fixture2_Threads = @(
    @{id = 'T1'; isResolved = $true; comments = @{nodes = @(@{databaseId = 1})}},
    @{id = 'T2'; isResolved = $true; comments = @{nodes = @(@{databaseId = 2})}}
)
# Expected: count = 0 (all resolved)
```

Fixture 3 - Mixed State:
```powershell
$Fixture3_Comments = @(
    @{id = 1; user = @{type = 'Bot'}; reactions = @{eyes = 0}},  # Unacknowledged
    @{id = 2; user = @{type = 'Bot'}; reactions = @{eyes = 1}},  # Acked, unresolved
    @{id = 3; user = @{type = 'Bot'}; reactions = @{eyes = 1}}   # Acked, resolved
)
$Fixture3_Threads = @(
    @{id = 'T1'; isResolved = $false; comments = @{nodes = @(@{databaseId = 1})}},
    @{id = 'T2'; isResolved = $false; comments = @{nodes = @(@{databaseId = 2})}},
    @{id = 'T3'; isResolved = $true; comments = @{nodes = @(@{databaseId = 3})}}
)
# Expected: count = 2 (IDs 1 and 2)
```

TEST CASES:
1. All resolved (Fixture 2) returns count = 0
2. Acknowledged but unresolved (Fixture 1) returns count = 5
3. Unacknowledged (eyes=0) returns count > 0
4. Mixed state (Fixture 3) returns only unaddressed (count = 2)
5. GraphQL API failure falls back to unacknowledged-only check
6. Non-bot comments are excluded

ACCEPTANCE CRITERIA:
- [ ] Test case: All resolved (eyes=1, isResolved=true) returns count = 0
- [ ] Test case: Acknowledged but unresolved (eyes=1, isResolved=false) returns count > 0
- [ ] Test case: Unacknowledged (eyes=0, isResolved=false) returns count > 0
- [ ] Test case: Mixed state returns only unaddressed comments
- [ ] Test case: GraphQL API failure falls back to unacknowledged-only check
- [ ] Test case: Non-bot comments are excluded
- [ ] All test fixtures from PRD Appendix are covered
- [ ] All tests pass with green status
```

---

## TASK-006: Update PR classification logic to use Get-UnaddressedComments

### Prompt for Implementer

```
Replace Get-UnacknowledgedComments with Get-UnaddressedComments at the integration point.

CONTEXT:
- File: scripts/Invoke-PRMaintenance.ps1
- Location: Line ~1401 (search for "Get-UnacknowledgedComments")
- This is a minimal change - variable rename and function swap only

CHANGE:
```powershell
# BEFORE (line ~1401)
$unacked = Get-UnacknowledgedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number -Comments $comments
$hasUnaddressedComments = $unacked.Count -gt 0

# AFTER
$unaddressed = Get-UnaddressedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number -Comments $comments
$hasUnaddressedComments = $unaddressed.Count -gt 0
```

IMPORTANT:
- Do NOT modify Get-UnacknowledgedComments function (preserve backward compatibility)
- Only change the function call and variable name
- Do NOT change surrounding logic

ACCEPTANCE CRITERIA:
- [ ] Line ~1401 calls Get-UnaddressedComments (not Get-UnacknowledgedComments)
- [ ] Variable name changed from $unacked to $unaddressed
- [ ] No other logic changes in surrounding code
- [ ] Code compiles without syntax errors
- [ ] Existing Get-UnacknowledgedComments function remains unchanged

VALIDATION:
```bash
pwsh -Command "& { . ./scripts/Invoke-PRMaintenance.ps1 -DryRun } 2>&1"
# Should not produce syntax errors
```
```

---

## TASK-007: Update ActionRequired reason to distinguish unresolved threads

### Prompt for Implementer

```
Add logic to distinguish UNRESOLVED_THREADS from UNACKNOWLEDGED in ActionRequired reason.

CONTEXT:
- File: scripts/Invoke-PRMaintenance.ps1
- Location: Near line ~1401, after the Get-UnaddressedComments call
- Depends on: TASK-006 integration point update

REQUIREMENTS:
The ActionRequired entry must indicate WHY a PR needs action:
- UNRESOLVED_THREADS: When threads are unresolved (even if acknowledged)
- UNACKNOWLEDGED: When comments lack eyes reaction
- UNRESOLVED_THREADS+UNACKNOWLEDGED: When both conditions exist

IMPLEMENTATION:
```powershell
# After calling Get-UnaddressedComments
$unaddressed = Get-UnaddressedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number -Comments $comments

if ($unaddressed.Count -gt 0) {
    # Determine reason based on state
    $unresolvedThreads = Get-UnresolvedReviewThreads -Owner $Owner -Repo $Repo -PR $pr.number
    $hasUnresolvedThreads = $unresolvedThreads.Count -gt 0
    $hasUnackedComments = ($unaddressed | Where-Object { $_.reactions.eyes -eq 0 }).Count -gt 0

    $reason = if ($hasUnresolvedThreads -and $hasUnackedComments) {
        'UNRESOLVED_THREADS+UNACKNOWLEDGED'
    } elseif ($hasUnresolvedThreads) {
        'UNRESOLVED_THREADS'
    } else {
        'UNACKNOWLEDGED'
    }

    $null = $results.ActionRequired.Add(@{
        PR = $pr.number
        Author = $authorLogin
        Reason = $reason
        Title = $pr.title
        Category = 'agent-controlled'
        Action = "/pr-review via pr-comment-responder ($($unaddressed.Count) comments)"
    })
}
```

ACCEPTANCE CRITERIA:
- [ ] Reason is UNRESOLVED_THREADS when threads are unresolved
- [ ] Reason is UNACKNOWLEDGED when comments lack eyes reaction
- [ ] Reason is combined when both conditions exist
- [ ] Reason field appears in ActionRequired output table
- [ ] Reason provides sufficient diagnostic info for maintainers
```

---

## TASK-008: Add graphql resource to rate limit check

### Prompt for Implementer

```
Update Test-RateLimitSafe to check graphql resource with threshold of 100.

CONTEXT:
- File: scripts/Invoke-PRMaintenance.ps1
- Location: Line ~207 (search for "Test-RateLimitSafe" or rate limit checking)
- This is a safety measure to prevent hitting GraphQL rate limits

FIND THE EXISTING CODE (around line 207):
```powershell
# Current rate limit resources checked
$resources = @('core', 'search')
```

CHANGE TO:
```powershell
# Add graphql resource with lower threshold
$resources = @(
    @{Name = 'core'; Threshold = 100},
    @{Name = 'search'; Threshold = 30},
    @{Name = 'graphql'; Threshold = 100}
)
```

OR if the current implementation is simpler:
```powershell
# Just add graphql to existing check
$resources = @('core', 'search', 'graphql')
```

ACCEPTANCE CRITERIA:
- [ ] graphql added to resource list
- [ ] Threshold set to 100 remaining calls (or matches existing pattern)
- [ ] Script exits early if graphql limit too low
- [ ] Warning message mentions graphql resource specifically
- [ ] Existing core/search resource checks remain unchanged

VALIDATION:
```bash
# Check the rate limit function works
pwsh -Command "& { . ./scripts/Invoke-PRMaintenance.ps1; Test-RateLimitSafe }"
```
```

---

## TASK-009: Create integration test for PR #365 scenario

### Prompt for Implementer

```
Add integration test using PR #365 data to verify correct classification.

CONTEXT:
- File: scripts/tests/Invoke-PRMaintenance.Tests.ps1
- Location: Add new Describe block tagged as "Integration"
- Uses Fixture 1 from PRD (5 comments with eyes=1, all threads unresolved)

TEST STRUCTURE:
```powershell
Describe "PR Maintenance Integration Tests" -Tag "Integration" {
    BeforeAll {
        . $PSScriptRoot/../Invoke-PRMaintenance.ps1
    }

    Context "PR #365 Scenario: Acknowledged but unresolved comments" {
        BeforeAll {
            # Mock comments (all acknowledged with eyes=1)
            $Script:MockComments = @(
                @{id = 1; user = @{type = 'Bot'; login = 'coderabbitai'}; reactions = @{eyes = 1}; body = 'Review comment 1'},
                @{id = 2; user = @{type = 'Bot'; login = 'cursor[bot]'}; reactions = @{eyes = 1}; body = 'Review comment 2'},
                @{id = 3; user = @{type = 'Bot'; login = 'coderabbitai'}; reactions = @{eyes = 1}; body = 'Review comment 3'},
                @{id = 4; user = @{type = 'Bot'; login = 'cursor[bot]'}; reactions = @{eyes = 1}; body = 'Review comment 4'},
                @{id = 5; user = @{type = 'Bot'; login = 'coderabbitai'}; reactions = @{eyes = 1}; body = 'Review comment 5'}
            )

            # Mock threads (all unresolved)
            $Script:MockThreadsJson = '{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[' +
                '{"id":"T1","isResolved":false,"comments":{"nodes":[{"databaseId":1}]}},' +
                '{"id":"T2","isResolved":false,"comments":{"nodes":[{"databaseId":2}]}},' +
                '{"id":"T3","isResolved":false,"comments":{"nodes":[{"databaseId":3}]}},' +
                '{"id":"T4","isResolved":false,"comments":{"nodes":[{"databaseId":4}]}},' +
                '{"id":"T5","isResolved":false,"comments":{"nodes":[{"databaseId":5}]}}' +
            ']}}}}}}'
        }

        It "Get-UnaddressedComments returns all 5 comments" {
            Mock Get-PRComments { return $Script:MockComments }
            Mock gh { param($api, $graphql, $f, $query) return $Script:MockThreadsJson } -ParameterFilter { $api -eq 'graphql' }

            $result = Get-UnaddressedComments -Owner "test" -Repo "repo" -PRNumber 365

            $result.Count | Should -Be 5
        }

        It "PR is classified as ActionRequired" {
            Mock Get-PRComments { return $Script:MockComments }
            Mock gh { return $Script:MockThreadsJson } -ParameterFilter { $args -contains 'graphql' }

            # Run classification logic...
            # Verify PR appears in ActionRequired
        }

        It "Reason indicates UNRESOLVED_THREADS" {
            # Verify reason field
        }
    }
}
```

ACCEPTANCE CRITERIA:
- [ ] Test uses Fixture 1 from PRD (5 comments with eyes=1, all threads unresolved)
- [ ] Test mocks Get-PRComments to return 5 bot comments
- [ ] Test mocks Get-UnresolvedReviewThreads to return 5 unresolved threads
- [ ] Test verifies Get-UnaddressedComments returns count = 5
- [ ] Test verifies PR is classified as ActionRequired
- [ ] Test verifies reason indicates UNRESOLVED_THREADS
- [ ] Test passes with green status
```

---

## TASK-010: Run script against live repo to validate PR #365 detection

### Prompt for Implementer

```
Execute the script against the live GitHub repository to validate PR #365 detection.

CONTEXT:
- Repository: rjmurillo/ai-agents
- PR to validate: #365
- Expected: PR #365 should appear in ActionRequired with UNRESOLVED_THREADS reason

EXECUTION STEPS:

1. Run script in DryRun mode first:
```bash
pwsh scripts/Invoke-PRMaintenance.ps1 -Owner rjmurillo -Repo ai-agents -MaxPRs 20 -DryRun
```

2. Verify PR #365 appears in ActionRequired output:
```
Expected output should include:
PRs Requiring Action:
| PR | Author | Category | Reason | Action |
|----|--------|----------|--------|--------|
| #365 | rjmurillo-bot | agent-controlled | UNRESOLVED_THREADS | /pr-review via pr-comment-responder (5 comments) |
```

3. Verify no false positives:
   - Resolved PRs should NOT appear in ActionRequired
   - PRs with all comments acknowledged AND resolved should NOT appear

4. Measure performance impact:
```bash
# Baseline (before changes)
time pwsh scripts/Invoke-PRMaintenance.ps1 -Owner rjmurillo -Repo ai-agents -MaxPRs 5 -DryRun

# After changes
time pwsh scripts/Invoke-PRMaintenance.ps1 -Owner rjmurillo -Repo ai-agents -MaxPRs 5 -DryRun

# Delta should be < 2 seconds
```

ACCEPTANCE CRITERIA:
- [ ] Script runs without errors
- [ ] PR #365 appears in ActionRequired section
- [ ] All 5 comments are flagged as unaddressed
- [ ] Reason field indicates UNRESOLVED_THREADS (not UNACKNOWLEDGED)
- [ ] No false positives (resolved PRs not flagged)
- [ ] Script runtime increase is < 2 seconds compared to baseline
- [ ] Output format matches Success Metrics acceptance gate from PRD

EVIDENCE TO CAPTURE:
- Full script output showing PR #365 in ActionRequired
- Reason field value
- Runtime comparison (before vs after)
```

---

## TASK-011: Update bot-author-feedback-protocol.md glossary

### Prompt for Implementer

```
Add "Acknowledged vs Resolved" entry to the protocol document glossary.

CONTEXT:
- File: .agents/architecture/bot-author-feedback-protocol.md
- Location: Find the "Glossary" section (or create if doesn't exist)
- Reference: PRD Design Considerations > Semantic Model

GLOSSARY ENTRY TO ADD:

```markdown
### Acknowledged vs Resolved

**Acknowledged**: A comment has received an eyes reaction (emoji), indicating the bot has seen and queued it for processing. This is a signal of receipt, not completion.

- Check: `reactions.eyes > 0`
- Function: `Get-UnacknowledgedComments` returns comments missing this state

**Resolved**: A review thread has been marked as resolved in GitHub, indicating the feedback has been addressed and the conversation is complete.

- Check: `isResolved = true` (via GraphQL API)
- Function: `Get-UnresolvedReviewThreads` returns threads missing this state

**Unaddressed**: A comment that is EITHER unacknowledged OR unresolved. This is the actionable state requiring attention.

- Check: `reactions.eyes = 0 OR isResolved = false`
- Function: `Get-UnaddressedComments` returns comments in this state

**Example - PR #365**: Had 5 bot comments with `reactions.eyes = 1` (acknowledged) but all threads had `isResolved = false` (unresolved). The old `Get-UnacknowledgedComments` missed these; the new `Get-UnaddressedComments` catches them.
```

ACCEPTANCE CRITERIA:
- [ ] Glossary entry defines "Acknowledged" state (eyes reaction added)
- [ ] Glossary entry defines "Resolved" state (thread marked resolved)
- [ ] Glossary entry clarifies distinction between states
- [ ] Entry references Get-UnaddressedComments function
- [ ] Entry includes example scenario (PR #365)
```

---

## TASK-012: Add "Acknowledged vs Resolved" section to protocol

### Prompt for Implementer

```
Create new protocol section explaining the state lifecycle model.

CONTEXT:
- File: .agents/architecture/bot-author-feedback-protocol.md
- Location: Add as new section after existing workflow sections
- Reference: PRD Design Considerations > Semantic Model

SECTION TO ADD:

```markdown
## Comment Lifecycle Model

### State Transitions

```text
[NEW] -> [ACKNOWLEDGED] -> [REPLIED] -> [RESOLVED]
```

| State | reactions.eyes | isResolved | Has Reply |
|-------|---------------|------------|-----------|
| NEW | 0 | false | No |
| ACKNOWLEDGED | > 0 | false | No |
| REPLIED | > 0 | false | Yes |
| RESOLVED | > 0 | true | Yes |

### Detection Functions

| Function | Detects States | Purpose |
|----------|---------------|---------|
| `Get-UnacknowledgedComments` | NEW only | Legacy check for unprocessed comments |
| `Get-UnresolvedReviewThreads` | NEW, ACKNOWLEDGED, REPLIED | GraphQL-based thread resolution check |
| `Get-UnaddressedComments` | NEW, ACKNOWLEDGED, REPLIED | Combined check for actionable comments |

### Why Both Checks Matter

**Problem (PR #365)**: The maintenance script used only `Get-UnacknowledgedComments`, which checked `reactions.eyes = 0`. PR #365 had 5 bot comments with `reactions.eyes = 1` (acknowledged), but all review threads remained unresolved. The script incorrectly reported "no action needed."

**Solution**: `Get-UnaddressedComments` checks BOTH:
1. `reactions.eyes = 0` (unacknowledged) - via REST API
2. `isResolved = false` (unresolved thread) - via GraphQL API

This ensures acknowledged-but-unresolved comments are not missed.

### Backward Compatibility

`Get-UnacknowledgedComments` remains unchanged for workflows that only need acknowledgment tracking. `Get-UnaddressedComments` is the recommended function for determining if action is required.
```

ACCEPTANCE CRITERIA:
- [ ] Section includes state transition diagram (NEW -> ACKNOWLEDGED -> REPLIED -> RESOLVED)
- [ ] Section defines state checks for each lifecycle stage
- [ ] Section explains how Get-UnacknowledgedComments vs Get-UnaddressedComments differ
- [ ] Section references PR #365 as motivating example
- [ ] Section follows protocol document structure and formatting
```

---

## TASK-013: Update function docstrings with lifecycle model

### Prompt for Implementer

```
Add comprehensive docstrings to Get-UnresolvedReviewThreads and Get-UnaddressedComments.

CONTEXT:
- File: scripts/Invoke-PRMaintenance.ps1
- Functions: Get-UnresolvedReviewThreads, Get-UnaddressedComments
- Reference: PowerShell comment-based help standards

DOCSTRINGS TO ADD:

```powershell
<#
.SYNOPSIS
    Retrieves review threads that remain unresolved for a pull request.

.DESCRIPTION
    Queries the GitHub GraphQL API to retrieve all review threads for a pull request
    and filters to those where isResolved = false. This function is part of the
    comment lifecycle model:

    [NEW] -> [ACKNOWLEDGED] -> [REPLIED] -> [RESOLVED]

    Use this function to detect threads in any state except RESOLVED.

    See: .agents/architecture/bot-author-feedback-protocol.md#comment-lifecycle-model

.PARAMETER Owner
    The GitHub repository owner (organization or user).

.PARAMETER Repo
    The GitHub repository name.

.PARAMETER PR
    The pull request number.

.OUTPUTS
    System.Object[]
    Array of thread objects with id, isResolved, and comments properties.
    Returns empty array if all threads are resolved or on API failure.

.EXAMPLE
    $threads = Get-UnresolvedReviewThreads -Owner "rjmurillo" -Repo "ai-agents" -PR 365
    # Returns 5 threads for PR #365 where isResolved = false

.NOTES
    - Requires authenticated gh CLI
    - Uses GraphQL API (counts against graphql rate limit)
    - Returns empty array on API failure (logs warning)
    - Follows Skill-PowerShell-002: Always returns array, never $null
#>
function Get-UnresolvedReviewThreads { ... }

<#
.SYNOPSIS
    Retrieves bot comments that are either unacknowledged OR in unresolved threads.

.DESCRIPTION
    Combines acknowledgment check (reactions.eyes) with thread resolution check
    (isResolved via GraphQL) to identify comments requiring action. This function
    addresses the gap where acknowledged comments were assumed to be resolved.

    Comment Lifecycle:
    [NEW] -> [ACKNOWLEDGED] -> [REPLIED] -> [RESOLVED]

    This function returns comments in states: NEW, ACKNOWLEDGED, REPLIED
    (any state except RESOLVED).

    See: .agents/architecture/bot-author-feedback-protocol.md#comment-lifecycle-model

.PARAMETER Owner
    The GitHub repository owner (organization or user).

.PARAMETER Repo
    The GitHub repository name.

.PARAMETER PRNumber
    The pull request number.

.PARAMETER Comments
    Optional. Pre-fetched comments array. If not provided, fetches via Get-PRComments.

.OUTPUTS
    System.Object[]
    Array of comment objects where user.type = 'Bot' AND
    (reactions.eyes = 0 OR comment is in unresolved thread).
    Returns empty array if all comments are addressed.

.EXAMPLE
    $unaddressed = Get-UnaddressedComments -Owner "rjmurillo" -Repo "ai-agents" -PRNumber 365
    # Returns 5 comments for PR #365 (acknowledged but unresolved)

.EXAMPLE
    $comments = Get-PRComments -Owner "rjmurillo" -Repo "ai-agents" -PRNumber 365
    $unaddressed = Get-UnaddressedComments -Owner "rjmurillo" -Repo "ai-agents" -PRNumber 365 -Comments $comments
    # Reuses pre-fetched comments for efficiency

.NOTES
    - Requires authenticated gh CLI
    - Makes one GraphQL call per invocation
    - Falls back to unacknowledged-only check on GraphQL failure
    - Preserves backward compatibility with Get-UnacknowledgedComments behavior
#>
function Get-UnaddressedComments { ... }
```

ACCEPTANCE CRITERIA:
- [ ] Docstring includes .SYNOPSIS describing function purpose
- [ ] Docstring includes .DESCRIPTION with lifecycle model reference
- [ ] Docstring includes .PARAMETER for each parameter
- [ ] Docstring includes .EXAMPLE showing typical usage
- [ ] Docstring includes .OUTPUTS describing return type
- [ ] Docstring follows PowerShell comment-based help standards
```

---

## Execution Order

```text
Critical Path:
TASK-001 → TASK-002 → TASK-003 (unit tests) → TASK-004 → TASK-005 (unit tests)
    → TASK-006 → TASK-007 → TASK-009 (integration test) → TASK-010 (live validation)

Parallel Track (after TASK-006):
TASK-008 (rate limits)
TASK-011 → TASK-012 → TASK-013 (documentation)
```

## Notes

- Each prompt is self-contained with all context needed for execution
- Acceptance criteria match the task breakdown document
- File paths and line numbers are approximate - verify before editing
- Use `Get-UnresolvedReviewThreads` pattern from Resolve-PRReviewThread.ps1 as reference
- Follow Skill-PowerShell-002: Functions must always return arrays, never $null
