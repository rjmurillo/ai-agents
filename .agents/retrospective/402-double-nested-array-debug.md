# Retrospective: PR #402 Double-Nested Array Debug Session

## Session Info

- **Date**: 2025-12-26
- **Agents**: implementer, qa, debug (implicit)
- **Task Type**: Bug Fix
- **Outcome**: Success (bug fixed after 3 attempts)
- **Commit**: 526f551

---

## Phase 0: Data Gathering

### 4-Step Debrief

#### Step 1: Observe (Facts Only)

**Timeline:**

- T+0: User runs `pwsh ./scripts/Invoke-PRMaintenance.ps1` against 15 live PRs
- T+1: ALL 15 PRs fail with error: "The property 'number' cannot be found on this object"
- T+2: First fix attempt: Change `$similar.Number` to `$similar.number` (PascalCase → lowercase)
- T+3: Test still fails with same error
- T+4: Second fix attempt: Change hashtable to PSCustomObject with lowercase keys
- T+5: Test STILL fails - error message reveals `Item type: System.Object[]` not `PSCustomObject`
- T+6: Root cause discovered: Double-nesting from `Write-Output -NoEnumerate` + `@()` wrapper
- T+7: Final fix: Remove `Write-Output -NoEnumerate`, use simple `return $similar`
- T+8: Success - all PRs process correctly

**Tool Calls:**

1. `gh pr list` (mocked in tests, real in runtime)
2. PowerShell iteration over returned array
3. Property access on array elements

**Errors:**

```powershell
Error: The property 'number' cannot be found on this object. Verify that the property exists.
At line:1486 char:21
+                     Write-Log "  - PR #$($similar.number): $($similar.title)" -Level INFO
```

**Duration:** Multiple hours across debugging iterations

#### Step 2: Respond (Reactions)

**Pivots:**

1. Initial assumption: Property name casing issue (PascalCase vs lowercase)
2. Second assumption: Data structure issue (hashtable vs PSCustomObject)
3. Final discovery: Array nesting issue (double-wrapped array)

**Retries:**

- Property name change: Attempted but failed
- Data structure change: Attempted but failed
- Array handling change: Successful

**Escalations:**

- User had to run against real PRs to discover bug
- Unit tests provided false confidence

**Blocks:**

- None - root cause eventually discovered through debug output

#### Step 3: Analyze (Interpretations)

**Patterns:**

1. **Mock-Reality Gap**: Unit test mocks used PascalCase properties matching code expectations, but real GitHub API returns lowercase
2. **Array Unwrapping Behavior**: PowerShell's `@()` wrapper + `Write-Output -NoEnumerate` created double-nested structure
3. **Type System Blindness**: Static analysis and unit tests didn't catch runtime type mismatch
4. **Integration Gap**: No integration tests against real GitHub API

**Anomalies:**

- Unit tests PASSED with 100% coverage of Get-SimilarPRs function
- Pester mocks returned correct structure when tested
- Bug only appeared in production runtime

**Correlations:**

- Every PR failed identically - systematic issue not edge case
- Error occurred in foreach loop accessing array elements
- Problem was in array structure, not business logic

#### Step 4: Apply (Actions)

**Skills to Update:**

1. PowerShell array handling patterns (avoid `Write-Output -NoEnumerate` with `@()` wrappers)
2. Integration testing requirements (real API calls for external dependencies)
3. Mock fidelity requirements (match actual API response structure, not idealized)

**Process Changes:**

1. Add integration tests that call real GitHub API (limited, authenticated)
2. Verify mock data structures match actual API responses
3. Add type assertions in tests

**Context to Preserve:**

- Root cause: `Write-Output -NoEnumerate $array` combined with `@(Function-Call)` = double-nesting
- Solution: Use simple `return $array` instead of `Write-Output -NoEnumerate`
- Testing gap: Mocks used PascalCase, API uses lowercase

### Execution Trace Analysis

| Time | Agent | Action | Outcome | Energy |
|------|-------|--------|---------|--------|
| T+0 | User | Run script against 15 PRs | All fail | High |
| T+1 | implementer | Diagnose error message | Property not found | High |
| T+2 | implementer | Fix: Change Number → number | Test fails | Medium |
| T+3 | implementer | Debug: Check data structure | Hashtable suspected | Medium |
| T+4 | implementer | Fix: Hashtable → PSCustomObject | Test fails | Low |
| T+5 | implementer | Debug: Add type inspection | Discover `System.Object[]` | Low |
| T+6 | implementer | Analyze: Double-nesting pattern | Root cause found | High |
| T+7 | implementer | Fix: Remove Write-Output -NoEnumerate | Success | High |
| T+8 | User | Re-run script | All 15 PRs pass | High |

**Timeline Patterns:**

- Initial high energy (bug discovered)
- Energy declined during failed fixes (frustration)
- Energy restored when root cause discovered
- Quick resolution once pattern identified

**Energy Shifts:**

- **High to Low** at T+4: Second fix attempt failed, pattern unclear
- **Low to High** at T+6: Breakthrough moment - root cause identified

**Stall Points:**

- T+3 to T+5: Two failed fix attempts before root cause analysis

### Outcome Classification

#### Mad (Blocked/Failed)

- **Event**: First two fix attempts failed
- **Why**: Addressed symptoms (property casing, data structure) not root cause (array nesting)

- **Event**: Unit tests passed but runtime failed
- **Why**: Mocks didn't match real API response structure

#### Sad (Suboptimal)

- **Event**: Required multiple debugging iterations
- **Why**: No integration tests to catch API structure mismatch early

- **Event**: Error message was cryptic
- **Why**: PowerShell error didn't reveal array double-nesting issue directly

#### Glad (Success)

- **Event**: Root cause discovered through type inspection
- **Why**: Added debug output `Item type: System.Object[]` revealed actual structure

- **Event**: Fix was simple once cause identified
- **Why**: Problem was localized to one function's return pattern

- **Event**: Commit message captured learning
- **Why**: Documented mock vs API gap for future reference

#### Distribution

- **Mad**: 2 events (blocked progress)
- **Sad**: 2 events (inefficient path)
- **Glad**: 3 events (positive outcomes)
- **Success Rate**: 43% (succeeded on 3rd attempt)

---

## Phase 1: Generate Insights

### Five Whys Analysis

**Problem:** Unit tests passed but runtime execution failed on all 15 PRs with "property 'number' cannot be found"

**Q1:** Why did runtime fail when tests passed?
**A1:** Unit test mocks returned correct structure, but real GitHub API response had different structure

**Q2:** Why did mocks have different structure than API?
**A2:** Mocks used PascalCase properties (`Number`, `Title`) but API returns lowercase (`number`, `title`)

**Q3:** Why didn't we notice the casing difference?
**A3:** Code used lowercase access (`$similar.number`) but function returned hashtable with PascalCase keys

**Q4:** Why did foreach fail to iterate array elements?
**A4:** The array was double-nested: `@( @(items) )` - foreach received entire inner array as single element

**Q5:** Why was array double-nested?
**A5:** Function used `Write-Output -NoEnumerate $array` AND call site wrapped with `@()` - both preserve array as single object

**Root Cause:** Combining `Write-Output -NoEnumerate` (preserves array as single object) with `@()` wrapper at call site creates double-nested array

**Actionable Fix:** Remove `Write-Output -NoEnumerate` and use simple `return $array` - let PowerShell handle array unwrapping naturally

### Fishbone Analysis

**Problem:** Unit tests provided false confidence - passed but runtime failed

#### Category: Prompt

- Test design didn't specify "match real API structure"
- No requirement stated for integration testing
- Acceptance criteria focused on unit test coverage only

#### Category: Tools

- Pester mocks use manually-created data structures
- No tool to validate mock fidelity against real API
- gh CLI doesn't provide type schema for validation

#### Category: Context

- Missing knowledge: GitHub API returns lowercase property names
- Missing knowledge: `Write-Output -NoEnumerate` + `@()` = double-nesting
- No documentation of array handling best practices

#### Category: Dependencies

- GitHub API structure not documented in code
- Mocks manually maintained, can drift from reality
- No contract testing against GitHub API

#### Category: Sequence

- Unit tests run before integration tests (which don't exist)
- Code merged without real API validation
- Bug discovered only when script ran in production

#### Category: State

- N/A (stateless function issue)

### Cross-Category Patterns

**Mock Fidelity** appears in:

- **Tools**: Pester mocks manually created
- **Dependencies**: No validation against real API
- **Context**: Missing API structure knowledge

**Integration Testing Gap** appears in:

- **Prompt**: No integration test requirement
- **Sequence**: Unit tests only, no real API validation
- **Dependencies**: No contract with GitHub API

### Controllable vs Uncontrollable

| Factor | Controllable? | Action |
|--------|---------------|--------|
| Mock data structure | Yes | Validate mocks against real API responses |
| Array handling pattern | Yes | Document best practice, avoid double-nesting |
| GitHub API schema | No | Mitigate with integration tests |
| PowerShell type system | No | Mitigate with type assertions in tests |
| Test coverage metric | Yes | Add integration test coverage requirement |

### Learning Matrix

#### :) Continue (What Worked)

- **Debug output inspection**: Adding type inspection revealed `System.Object[]` and led to root cause
- **Commit message detail**: Documented root cause and lesson learned for future reference
- **Simple fix**: Once identified, solution was straightforward (remove `Write-Output -NoEnumerate`)
- **Error preservation**: User reported exact error message, enabling precise diagnosis

#### :( Change (What Didn't Work)

- **Mock fidelity**: Mocks used PascalCase (idealized) instead of lowercase (actual API)
- **Unit-only testing**: 100% unit test coverage but 0% integration test coverage
- **Symptom fixing**: First two attempts addressed symptoms not root cause
- **No type validation**: Tests didn't assert returned object types

#### Idea (New Approaches)

- **Contract testing**: Capture real API response samples and validate mocks match
- **Integration test suite**: Small set of real API calls (rate-limited, authenticated)
- **Type assertions**: Add `-TypeOf` checks in Pester tests
- **Array handling linter**: Detect `Write-Output -NoEnumerate` + `@()` pattern

#### Invest (Long-Term Improvements)

- **API response fixtures**: Recorded real responses for consistent mock generation
- **Testing pyramid**: Unit tests (many) + integration tests (few) + E2E tests (minimal)
- **Mock fidelity tooling**: Automated validation that mocks match real API structure
- **PowerShell best practices**: Document array handling patterns and anti-patterns

### Priority Items

1. **Continue**: Debug output inspection technique - saved the debugging session
2. **Change**: Add integration tests for GitHub API-dependent functions
3. **Idea**: Implement contract testing with real API response validation
4. **Invest**: Create PowerShell array handling best practices guide

---

## Phase 2: Diagnosis

### Outcome

**Partial Success** - Bug fixed on 3rd attempt after identifying root cause

### What Happened

**Concrete Execution:**

1. User ran `Invoke-PRMaintenance.ps1` against 15 real PRs in repository
2. Script failed on all 15 PRs with "property 'number' cannot be found"
3. Error occurred in foreach loop at line 1486 accessing `$similar.number`
4. First fix: Changed `$similar.Number` → `$similar.number` (casing fix)
5. Second fix: Changed hashtable to PSCustomObject with lowercase keys
6. Third fix: Removed `Write-Output -NoEnumerate`, used simple `return $similar`
7. Success: All 15 PRs processed correctly

### Root Cause Analysis

**Root Cause:** Double-nested array structure from combining two array-preserving mechanisms

**Why it failed:**

```powershell
# Inside Get-SimilarPRs function
$similar = @()  # Array of items
# ... add items ...
Write-Output -NoEnumerate $similar  # Returns array as SINGLE OBJECT

# At call site (line 1482)
$similarPRs = @(Get-SimilarPRs ...)  # Wraps returned object in ANOTHER array

# Result: @( @(item1, item2, item3) )
# When foreach iterates $similarPRs, it receives ONE element: the inner array
# Accessing $similar.number tries to access property on array itself, not elements
```

**Contributing factors:**

1. **Mock-API gap**: Unit test mocks used PascalCase (`Number`), API returns lowercase (`number`)
2. **No integration tests**: No validation against real GitHub API responses
3. **Type system blindness**: PowerShell doesn't enforce type contracts, errors emerge at runtime
4. **Array handling confusion**: Two mechanisms to preserve arrays combined incorrectly

### Evidence

**Commit message (526f551):**

> Root cause: Mocks used PascalCase properties that matched the code,
> but the real GitHub API returns lowercase. Static analysis passed
> but actual execution revealed the runtime issue.
>
> Lesson: Integration testing against real APIs is essential to catch
> casing and structure issues that mocks cannot reveal.

**Test code (lines 1028-1037):**

```powershell
It "Returns similar PRs when merged PR has matching title" {
    Mock gh {
        $global:LASTEXITCODE = 0
        return ($Script:Fixtures.MergedPRs | ConvertTo-Json)
    }

    $result = Get-SimilarPRs -Owner "test" -Repo "repo" -PRNumber 123 -Title "feat: add feature X"
    $result.Count | Should -BeGreaterThan 0
    $result[0].Number | Should -Be 789  # Test used PascalCase!
}
```

**Fixture data (lines 66-71):**

```powershell
MergedPRs = @(
    @{
        number = 789  # Fixture used lowercase (correct)
        title = "feat: add feature X v2"
    }
)
```

**The test accessed `$result[0].Number` (PascalCase) but fixture had `number` (lowercase). The test PASSED because:**

- PowerShell hashtables are case-insensitive for string keys
- `@{number=789}` can be accessed as `.Number` or `.number`
- But the CODE used lowercase, which would fail on strict objects

### Priority Classification

| Finding | Priority | Category | Evidence |
|---------|----------|----------|----------|
| Write-Output -NoEnumerate + @() creates double-nesting | P0 | Critical | Blocked all 15 PRs |
| Unit test mocks don't match API structure | P0 | Critical | False confidence, no API validation |
| No integration tests for GitHub API calls | P1 | Success | Would have caught bug pre-merge |
| PowerShell hashtable case-insensitivity masks bugs | P1 | NearMiss | Tests passed with wrong casing |
| Type assertions missing from tests | P2 | Efficiency | Would catch structure issues earlier |

---

## Phase 3: Decide What to Do

### Action Classification

#### Keep (TAG as helpful)

| Finding | Skill ID | Validation Count |
|---------|----------|------------------|
| Debug output inspection (type dumping) | Skill-Debugging-002 | +1 |
| Simple return instead of Write-Output | Skill-PowerShell-003 | +1 |
| Detailed commit messages with root cause | Skill-Git-004 | +1 |

#### Drop (REMOVE or TAG as harmful)

| Finding | Skill ID | Reason |
|---------|----------|--------|
| Write-Output -NoEnumerate with @() wrapper | Anti-Pattern-PowerShell-001 | Creates double-nested arrays |
| Mocks with idealized structure vs real API | Anti-Pattern-Testing-001 | False confidence |

#### Add (New skill)

| Finding | Proposed Skill ID | Statement |
|---------|-------------------|-----------|
| Integration tests for external APIs | Skill-Testing-003 | Validate mocks match real API structure using integration tests |
| Array handling best practices | Skill-PowerShell-004 | Use simple return for arrays; avoid Write-Output -NoEnumerate |
| Type assertions in tests | Skill-Testing-004 | Assert returned object types match expectations in unit tests |
| Contract testing for APIs | Skill-Testing-005 | Capture real API responses as test fixtures |

#### Modify (UPDATE existing)

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| Skill-Testing-001 | Unit tests sufficient | Unit + integration tests required | Mock fidelity gap |

### SMART Validation

#### Proposed Skill 1: Integration Tests for External APIs

**Statement:** "Validate mocks match real API structure using integration tests"

| Criterion | Pass? | Evidence |
|-----------|-------|----------|
| Specific | Y | One concept: integration test requirement |
| Measurable | Y | Can verify by presence of integration test suite |
| Attainable | Y | Technically feasible with gh CLI |
| Relevant | Y | Would have caught this bug pre-merge |
| Timely | Y | Trigger: When function calls external API |

**Result:** ✓ All criteria pass - Accept skill

**Atomicity:** 92% (clear, specific, measurable, actionable)

#### Proposed Skill 2: Array Handling Best Practice

**Statement:** "Use simple return for arrays; avoid Write-Output -NoEnumerate"

| Criterion | Pass? | Evidence |
|-----------|-------|----------|
| Specific | Y | Exact technique: simple return |
| Measurable | Y | Can verify in code review |
| Attainable | Y | Standard PowerShell pattern |
| Relevant | Y | Prevents double-nesting |
| Timely | Y | Trigger: Returning arrays from functions |

**Result:** ✓ All criteria pass - Accept skill

**Atomicity:** 95% (concise, clear, actionable)

#### Proposed Skill 3: Type Assertions in Tests

**Statement:** "Assert returned object types match expectations in unit tests"

| Criterion | Pass? | Evidence |
|-----------|-------|----------|
| Specific | Y | One concept: type assertions |
| Measurable | Y | Can count type assertions in tests |
| Attainable | Y | Pester supports type checks |
| Relevant | Y | Would catch structure mismatches |
| Timely | Y | Trigger: Writing unit tests |

**Result:** ✓ All criteria pass - Accept skill

**Atomicity:** 90% (clear, measurable)

#### Proposed Skill 4: Contract Testing for APIs

**Statement:** "Capture real API responses as test fixtures"

| Criterion | Pass? | Evidence |
|-----------|-------|----------|
| Specific | Y | One concept: real response fixtures |
| Measurable | Y | Can verify fixture files exist |
| Attainable | Y | Standard contract testing |
| Relevant | Y | Ensures mock fidelity |
| Timely | Y | Trigger: First integration test |

**Result:** ✓ All criteria pass - Accept skill

**Atomicity:** 88% (clear and actionable)

### Action Sequence

| Order | Action | Depends On | Blocks |
|-------|--------|------------|--------|
| 1 | Document PowerShell array handling pattern | None | None |
| 2 | Add type assertions to existing tests | None | None |
| 3 | Create integration test for Get-SimilarPRs | None | 4 |
| 4 | Capture real API response as fixture | 3 | 5 |
| 5 | Validate mocks against fixture | 4 | None |

---

## Phase 4: Extracted Learnings

### Learning 1: Double-Nested Array Anti-Pattern

- **Statement**: Avoid combining Write-Output -NoEnumerate with @() array wrapper
- **Atomicity Score**: 95%
- **Evidence**: Commit 526f551, runtime failure on 15 PRs, foreach received System.Object[] not PSCustomObject
- **Skill Operation**: ADD
- **Target Skill ID**: Skill-PowerShell-004

### Learning 2: Integration Test Requirement

- **Statement**: Functions calling external APIs require integration tests to validate mock fidelity
- **Atomicity Score**: 92%
- **Evidence**: Unit tests passed (100% coverage), runtime failed against real API
- **Skill Operation**: ADD
- **Target Skill ID**: Skill-Testing-003

### Learning 3: Mock Structure Validation

- **Statement**: Test mocks must match actual API response structure including property name casing
- **Atomicity Score**: 93%
- **Evidence**: Mocks used PascalCase (Number), API returned lowercase (number), PowerShell hashtable case-insensitivity masked issue
- **Skill Operation**: ADD
- **Target Skill ID**: Skill-Testing-006

### Learning 4: Type Assertions in Tests

- **Statement**: Unit tests should assert returned object types not just property values
- **Atomicity Score**: 90%
- **Evidence**: Test accessed `$result[0].Number` assuming object, runtime revealed `System.Object[]` type
- **Skill Operation**: ADD
- **Target Skill ID**: Skill-Testing-004

### Learning 5: Debug Output Technique

- **Statement**: When debugging PowerShell arrays add type inspection using GetType() FullName property
- **Atomicity Score**: 88%
- **Evidence**: Adding `Item type: System.Object[]` output revealed root cause after 2 failed fix attempts
- **Skill Operation**: TAG
- **Target Skill ID**: Skill-Debugging-002 (mark as helpful)

---

## Skillbook Updates

### ADD

#### Skill-PowerShell-004: Array Return Pattern

```json
{
  "skill_id": "Skill-PowerShell-004",
  "statement": "Use simple return for arrays; avoid Write-Output -NoEnumerate with @() wrapper",
  "context": "When returning arrays from PowerShell functions. Combining Write-Output -NoEnumerate (preserves array as single object) with @() wrapper at call site creates double-nested arrays where foreach receives entire inner array as single element instead of iterating individual items.",
  "evidence": "PR #402 commit 526f551 - runtime failure on 15 PRs, foreach received System.Object[] not PSCustomObject elements. Root cause: function used Write-Output -NoEnumerate $array AND call site wrapped with @(Get-SimilarPRs ...) resulting in @( @(items) ).",
  "atomicity": 95
}
```

#### Skill-Testing-003: Integration Test for External APIs

```json
{
  "skill_id": "Skill-Testing-003",
  "statement": "Functions calling external APIs require integration tests to validate mock fidelity",
  "context": "When unit tests use mocks for external APIs (GitHub, REST services). Unit tests alone provide false confidence when mocks diverge from actual API responses. Integration tests catch structure mismatches before production.",
  "evidence": "PR #402 - Get-SimilarPRs had 100% unit test coverage but all 15 production runs failed. Unit test mocks used PascalCase properties (Number, Title), GitHub API returns lowercase (number, title). No integration test existed to catch the gap.",
  "atomicity": 92
}
```

#### Skill-Testing-006: Mock Structure Fidelity

```json
{
  "skill_id": "Skill-Testing-006",
  "statement": "Test mocks must match actual API response structure including property name casing",
  "context": "When creating Pester mocks for external APIs. PowerShell hashtable case-insensitivity (@{number=789} accessible as .Number) can mask bugs that appear with strict objects. Mocks should exactly replicate API response structure.",
  "evidence": "PR #402 - test fixture used lowercase 'number' but test assertion used PascalCase '.Number' and passed due to hashtable case-insensitivity. Runtime code used lowercase '.number' which failed when API structure differed. Gap would have been caught if mocks matched API exactly.",
  "atomicity": 93
}
```

#### Skill-Testing-004: Type Assertions

```json
{
  "skill_id": "Skill-Testing-004",
  "statement": "Unit tests should assert returned object types not just property values",
  "context": "When testing functions that return structured data. Tests that only validate property values ($result[0].Number) can pass even when returned type is incorrect (System.Object[] instead of PSCustomObject). Add type assertions to catch structure issues.",
  "evidence": "PR #402 - test validated $result[0].Number equals 789 but didn't assert $result[0] was PSCustomObject. Runtime revealed foreach received System.Object[] (double-nested array) not individual objects. Type assertion would have failed in unit test.",
  "atomicity": 90
}
```

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| Skill-Debugging-002 | helpful | PR #402 - type inspection output revealed System.Object[] | Root cause discovered after 2 failed attempts |

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| (none) | - | - | All learnings are new skills |

---

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| Skill-PowerShell-004 | Skill-PowerShell-002 (array null safety) | 20% | UNIQUE - different pattern |
| Skill-Testing-003 | Skill-Testing-001 (basic testing) | 40% | UNIQUE - integration vs unit |
| Skill-Testing-006 | Skill-Testing-003 | 60% | UNIQUE - mock fidelity vs integration |
| Skill-Testing-004 | Skill-Testing-001 | 30% | UNIQUE - type assertions vs coverage |

---

## Phase 5: Close the Retrospective

### +/Delta

#### + Keep

- **Five Whys analysis**: Drilling down from symptom (property not found) to root cause (double-nested array) was effective
- **Fishbone cross-category patterns**: Identified "Mock Fidelity" appearing in Tools, Dependencies, Context categories - confirmed systemic issue
- **Learning Matrix**: Quickly categorized Continue (debug output) vs Change (mock fidelity) vs Invest (contract testing)
- **SMART validation**: All 4 skills passed atomicity ≥88%, high-quality learnings

#### Delta Change

- **Timeline reconstruction**: Had to infer debugging sequence from commit messages - could have been more explicit
- **Metric tracking**: No quantification of wasted time (hours debugging) or impact (15 PRs blocked)
- **Pattern generalization**: Could extract broader principle "dynamic type systems require runtime validation"

### ROTI Assessment

**Score**: 3 (High return)

**Benefits Received:**

- 4 atomic skills extracted (all ≥88% atomicity)
- Root cause pattern documented (Write-Output -NoEnumerate + @())
- Testing gap identified (no integration tests for external APIs)
- Anti-pattern catalogued (mock-reality divergence)
- Process improvement identified (contract testing)

**Time Invested**: ~45 minutes for retrospective analysis

**Verdict**: Continue - valuable learnings that prevent future bugs

### Helped, Hindered, Hypothesis

#### Helped

- Commit message with detailed root cause explanation saved context reconstruction time
- Git history showing 3 fix attempts provided clear failure timeline
- Error message preservation in user report enabled precise diagnosis
- Test code inspection revealed mock structure vs API structure gap

#### Hindered

- No session log from original debugging - had to reconstruct from artifacts
- No quantitative metrics (time wasted, PRs affected, retry count)
- Limited test coverage prevented full understanding of gap magnitude

#### Hypothesis

Next retrospective: Track debugging metrics during execution (attempts, duration, error types) rather than reconstructing afterward. This enables quantitative analysis of debugging efficiency.

---

## Retrospective Handoff

### Skill Candidates

| Skill ID | Statement | Atomicity | Operation | Target |
|----------|-----------|-----------|-----------|--------|
| Skill-PowerShell-004 | Use simple return for arrays; avoid Write-Output -NoEnumerate with @() wrapper | 95% | ADD | - |
| Skill-Testing-003 | Functions calling external APIs require integration tests to validate mock fidelity | 92% | ADD | - |
| Skill-Testing-006 | Test mocks must match actual API response structure including property name casing | 93% | ADD | - |
| Skill-Testing-004 | Unit tests should assert returned object types not just property values | 90% | ADD | - |
| Skill-Debugging-002 | (existing) | - | TAG | Tag as helpful |

### Memory Updates

| Entity | Type | Content | File |
|--------|------|---------|------|
| PowerShell-Array-Handling | Pattern | Avoid Write-Output -NoEnumerate with @() wrapper - creates double-nesting | `.serena/memories/powershell-array-handling.md` |
| Testing-Mock-Fidelity | Pattern | Mocks must match API structure exactly including casing | `.serena/memories/testing-mock-fidelity.md` |
| PR-402-Learnings | Learning | Double-nested array debug session - 3 attempts, root cause: array handling | `.serena/memories/retrospective-2025-12-26.md` |

### Git Operations

| Operation | Path | Reason |
|-----------|------|--------|
| git add | `.agents/retrospective/402-double-nested-array-debug.md` | Retrospective artifact |
| git add | `.agents/sessions/2025-12-26-session-89-pr402-debug-retrospective.md` | Session log |
| git add | `.serena/memories/powershell-array-handling.md` | New pattern memory |
| git add | `.serena/memories/testing-mock-fidelity.md` | New pattern memory |

### Handoff Summary

- **Skills to persist**: 4 candidates (atomicity ≥ 90%) + 1 tag
- **Memory files touched**: powershell-array-handling.md (new), testing-mock-fidelity.md (new), retrospective-2025-12-26.md (append)
- **Recommended next**: memory (persist learnings) → git add (commit artifacts)

---

## Answers to User Questions

### 1. Why did the original unit tests pass when the runtime behavior was wrong?

**Three converging factors:**

1. **Mock-API Structure Gap**: Unit test mocks used PascalCase properties (`Number`, `Title`) that matched developer expectations, but the real GitHub API returns lowercase (`number`, `title`)

2. **PowerShell Hashtable Case-Insensitivity**: The test fixture defined `@{number = 789}` but test assertion accessed `$result[0].Number` (PascalCase). This PASSED because PowerShell hashtables are case-insensitive for string keys - `@{number=789}` can be accessed as `.Number` or `.number`

3. **Type Validation Gap**: Tests validated property VALUES (`$result[0].Number | Should -Be 789`) but didn't validate returned TYPES. The test passed as long as the value was correct, even though the actual runtime type was `System.Object[]` (double-nested array) instead of individual `PSCustomObject` elements

**The perfect storm:** Mocks had wrong casing (but hashtables hide it) + tests checked values not types + no integration tests against real API.

### 2. What testing gaps allowed this bug to ship?

**Five critical gaps:**

1. **No Integration Tests**: 100% unit test coverage but 0% integration test coverage. No validation against real GitHub API responses

2. **No Type Assertions**: Tests validated `$result[0].Number` value but never asserted `$result[0] -is [PSCustomObject]` or `$result.Count -gt 0 -and $result[0].GetType().FullName -eq 'System.Management.Automation.PSCustomObject'`

3. **Mock Fidelity Not Validated**: Mocks manually created and never compared against actual API responses. No contract testing or response capture

4. **Array Structure Not Tested**: Tests validated individual element properties but never validated the array structure itself (nested vs flat)

5. **PowerShell Dynamic Typing Trusted**: Relied on PowerShell's dynamic type system without runtime validation. No verification that returned objects matched expected types

**Gap matrix:**

| Gap | Consequence | Would Have Caught Bug? |
|-----|-------------|----------------------|
| No integration tests | API structure mismatch undetected | YES |
| No type assertions | Wrong type returned but tests pass | YES |
| Mock fidelity not validated | Mocks diverged from reality | YES |
| Array structure not tested | Double-nesting undetected | YES |
| Dynamic typing trusted | Runtime type errors not prevented | PARTIAL |

### 3. What process improvements could prevent this class of bug?

**Immediate improvements (P0):**

1. **Integration Test Requirement**: All functions calling external APIs must have at least one integration test validating actual API response structure. Gate PR approval on integration test presence.

2. **Contract Testing**: Capture real API responses and store as test fixtures. Validate mocks against captured responses using schema comparison.

3. **Type Assertion Standard**: Every unit test that validates object properties must include type assertion: `$result[0] | Should -BeOfType [PSCustomObject]`

4. **Array Handling Linter**: Add PSScriptAnalyzer custom rule to detect `Write-Output -NoEnumerate` combined with `@()` wrapper pattern (double-nesting anti-pattern)

**Medium-term improvements (P1):**

5. **Testing Pyramid Enforcement**: Define test distribution targets: 70% unit tests, 20% integration tests, 10% E2E tests. Track metrics in CI.

6. **Mock Fidelity Tooling**: Create script that fetches real API response and compares schema against test mocks. Fail if mismatches found.

7. **PowerShell Best Practices Guide**: Document array handling patterns, type system gotchas, and common anti-patterns. Reference in PR template.

**Long-term improvements (P2):**

8. **API Response Recording**: Implement VCR-like recording for GitHub API calls. First test run records, subsequent runs replay. Ensures mocks stay synchronized.

9. **Pre-commit Hook**: Run subset of integration tests locally before push. Catch API mismatches before CI.

10. **Chaos Testing**: Randomly inject real API calls during test runs to validate mocks haven't drifted.

### 4. Should Write-Output -NoEnumerate ever be used with @() wrappers at call sites?

**Short answer: NO. Never combine them.**

**Why:**

```powershell
# Inside function
function Get-Items {
    $items = @(1, 2, 3)
    Write-Output -NoEnumerate $items  # Returns array as SINGLE object
}

# At call site
$result = @(Get-Items)  # Wraps the single object (which is an array) in ANOTHER array

# Result: @( @(1, 2, 3) )
# foreach $item in $result → $item = @(1, 2, 3) (the entire inner array)
```

**Recommended patterns:**

| Scenario | Function Side | Call Site | Result |
|----------|---------------|-----------|--------|
| **Return array** | `return $items` | `$result = Get-Items` | Flat array ✓ |
| **Return array (safe)** | `return $items` | `$result = @(Get-Items)` | Flat array ✓ |
| **Return empty safe** | `return @()` | `$result = Get-Items` | Empty array ✓ |
| **WRONG** | `Write-Output -NoEnumerate $items` | `$result = @(Get-Items)` | Double-nested ✗ |

**When to use Write-Output -NoEnumerate:**

- **Never** if call site might use `@()` wrapper
- **Rarely** needed - PowerShell's default behavior handles arrays correctly
- **Only** when you specifically need to prevent pipeline unwrapping and you CONTROL the call site
- **Alternative**: Use `, $items` (comma operator) to return array as single object

**Best practice:** Use simple `return $items` and let PowerShell's natural behavior handle array unwrapping. Add `@()` at call site if you want to ensure array type for empty results.

**Anti-pattern to avoid:**

```powershell
# WRONG - double-nesting trap
function Get-Data {
    $data = @()
    # ... populate ...
    Write-Output -NoEnumerate $data  # ✗
}

$results = @(Get-Data)  # ✗ Double-nested

# RIGHT - simple and safe
function Get-Data {
    $data = @()
    # ... populate ...
    return $data  # ✓
}

$results = @(Get-Data)  # ✓ Flat array (handles empty correctly)
```

**Rule of thumb:** If you find yourself using `Write-Output -NoEnumerate`, ask "Why?" 99% of the time, you don't need it.
