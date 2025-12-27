# Retrospective Sessions - December 26, 2025

**Date**: 2025-12-26
**Domain**: Learning Extraction

## Session 89: PR #402 Double-Nested Array Debug

**Artifact**: `.agents/retrospective/402-double-nested-array-debug.md`
**Commit**: Analysis of debugging session for 526f551

### Key Learnings

1. **PowerShell Array Anti-Pattern**: Combining `Write-Output -NoEnumerate` with `@()` wrapper creates double-nested arrays
2. **Mock Fidelity Gap**: Unit test mocks used PascalCase properties, GitHub API returns lowercase
3. **Integration Test Requirement**: 100% unit test coverage insufficient without integration tests
4. **Type Validation**: Tests validated property values but not returned object types

### Skills Extracted

- **Skill-PowerShell-004**: Array return pattern (95% atomicity)
- **Skill-Testing-003**: Integration test requirement (92% atomicity)
- **Skill-Testing-006**: Mock structure fidelity (93% atomicity)
- **Skill-Testing-004**: Type assertions (90% atomicity)

### Root Cause

**Bug**: `foreach ($similar in $similarPRs)` received entire inner array as single element instead of iterating individual items

**Why**: Function used `Write-Output -NoEnumerate $similar` AND call site used `$similarPRs = @(Get-SimilarPRs ...)` resulting in `@( @(items) )` structure

**Fix**: Remove `Write-Output -NoEnumerate`, use simple `return $similar`

### Impact

- **Runtime failures**: 15 out of 15 PRs failed
- **Fix attempts**: 3 iterations before root cause identified
- **Testing gap**: Unit tests 100% coverage but provided false confidence

### Related Memories

- **powershell-array-handling.md**: Detailed array handling best practices
- **testing-mock-fidelity.md**: Mock fidelity and integration test requirements
- **pester-testing-patterns.md**: General testing patterns
