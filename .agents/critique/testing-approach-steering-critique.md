# Critique: testing-approach.md Steering File

**Document**: `.agents/steering/testing-approach.md`
**Issue**: #571
**Date**: 2025-12-30
**Reviewer**: critic

## Verdict

**[APPROVED]**

## Summary

The testing-approach.md steering file accurately reflects the project's Pester 5.x testing patterns with comprehensive coverage of structural validation, functional testing, parameterized tests, test isolation, and cross-platform considerations. All examples match actual codebase patterns. No inaccuracies or contradictions found.

## Strengths

### Accurate Pattern Documentation

1. **BeforeAll/BeforeEach Usage**: Examples match actual test files
   - BeforeAll for expensive setup (line 140-143)
   - BeforeEach for test isolation (line 146-162)
   - Pattern verified in 60+ test files

2. **Parameterized Tests (-ForEach)**: Correct Pester 5.x syntax
   - Lines 116-124 show correct `-ForEach @()` parameter syntax
   - Verified in QualityGatePrompts.Tests.ps1 and Install-Common.Tests.ps1
   - Anti-pattern (Pester 4.x foreach loops) correctly identified

3. **Test Isolation Requirements**: Matches memory `pester-testing-test-isolation`
   - Lines 166-180 correctly document BeforeEach cleanup pattern
   - Example matches Validate-PlanningArtifacts.Tests.ps1 pattern
   - Rationale correctly explains test pollution prevention

4. **Cross-Platform Path Assertions**: Matches memory `pester-testing-cross-platform`
   - Lines 186-197 correctly use `[\\/]` regex alternation
   - Example matches Test-PRMerged.Tests.ps1 patterns
   - Anti-pattern (hardcoded separators) correctly identified

5. **Contract Testing**: Matches memory `testing-007-contract-testing`
   - Lines 201-227 accurately document API mock casing requirements
   - Type assertion examples match Invoke-CopilotAssignment.Tests.ps1
   - Rationale correctly explains PowerShell case-insensitivity masking issues

### Comprehensive Coverage

1. **Test File Structure** (lines 19-55): Matches actual test file headers
   - #Requires -Modules Pester
   - Comment-based help
   - BeforeAll for script loading
   - Describe > Context > It hierarchy

2. **Testing Strategies** (lines 59-107):
   - Pattern-based structural validation
   - Functional behavioral validation
   - AAA (Arrange-Act-Assert) pattern
   - Examples from Test-PRMerged.Tests.ps1 and Invoke-CopilotAssignment.Tests.ps1

3. **Anti-Patterns** (lines 320-388):
   - Test interdependencies
   - Missing BeforeEach cleanup
   - Idealized mock data
   - Assertions without type checks

### Practical Examples

All examples are extracted from actual test files:

- Comment-based help testing (lines 232-254): Test-PRMerged.Tests.ps1
- GraphQL query structure (lines 256-278): Test-PRMerged.Tests.ps1
- Error handling (lines 280-297): Test-PRMerged.Tests.ps1
- Exit code testing (lines 299-318): Test-PRMerged.Tests.ps1

## Issues Found

### Critical (Must Fix)

None.

### Important (Should Fix)

None.

### Minor (Consider)

None.

## Markdown Formatting

Validation passed with no errors:

```
npx markdownlint-cli2 .agents/steering/testing-approach.md
Summary: 0 error(s)
```

## Alignment with Project Patterns

### Verified Against Codebase

1. **BeforeEach Pattern**: Found in 60+ test files
   - Validate-PlanningArtifacts.Tests.ps1
   - Invoke-PesterTests.Tests.ps1
   - Validate-PathNormalization.Tests.ps1
   - Validate-MemoryIndex.Tests.ps1

2. **-ForEach Parameterized Tests**: Found in 2 test files
   - QualityGatePrompts.Tests.ps1 (7 instances)
   - Install-Common.Tests.ps1 (1 instance)

3. **Pattern-Based + Functional Tests**: Documented strategy
   - Test-PRMerged.Tests.ps1 (477 lines, 100% coverage)
   - Invoke-CopilotAssignment.Tests.ps1 (1376 lines, mixed approach)

4. **Contract Testing**: Validated in PR #402 retrospective
   - Memory: `testing-007-contract-testing`
   - Memory: `testing-mock-fidelity`

### Verified Against Memory System

1. **pester-testing-test-isolation**: Lines 166-180 match memory exactly
2. **testing-007-contract-testing**: Lines 201-227 match memory exactly
3. **pester-testing-cross-platform**: Lines 186-197 match memory exactly

## Coverage Expectations (Lines 389-405)

Appropriate level of detail:

- Target: ≥80% code coverage for happy paths
- Required areas documented
- References to example implementations provided

## References Section (Lines 399-405)

All references verified:

- Test-PRMerged.Tests.ps1: Exists at documented path
- Invoke-CopilotAssignment.Tests.ps1: Exists at documented path
- Memory references: All exist in Serena memory system

## Scope Alignment

**Applies to**: `**/*.Tests.ps1`

Correctly scoped to Pester test files only. Does not overreach into:

- Integration testing
- Performance testing
- Manual QA processes

## Detail Level Assessment

Appropriate for a steering file:

- Not a tutorial (assumes Pester knowledge)
- Focuses on project-specific patterns
- Provides rationale for each pattern
- Links to reference implementations

## Recommendations

None. Document is ready for use as an active steering file.

## Approval Conditions

All conditions met:

- [x] All examples verified against actual codebase patterns
- [x] No inaccurate claims or contradictions
- [x] Proper markdown formatting (0 lint errors)
- [x] Appropriate level of detail for steering file
- [x] Aligned with project memory system
- [x] References validated
- [x] Anti-patterns correctly identified
- [x] Scope correctly defined

## Next Steps

Document approved for merge. No revisions required.
