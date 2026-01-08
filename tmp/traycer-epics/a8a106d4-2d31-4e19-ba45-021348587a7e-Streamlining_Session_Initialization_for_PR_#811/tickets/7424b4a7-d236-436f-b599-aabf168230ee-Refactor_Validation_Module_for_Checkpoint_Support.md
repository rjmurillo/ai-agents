---
id: "7424b4a7-d236-436f-b599-aabf168230ee"
title: "Refactor Validation Module for Checkpoint Support"
assignee: ""
status: 0
createdAt: "1767766906923"
updatedAt: "1767767891043"
type: ticket
---

# Refactor Validation Module for Checkpoint Support

## Objective

Extract validation logic from file:scripts/Validate-SessionProtocol.ps1 into reusable functions in file:scripts/modules/SessionValidation.psm1 to enable granular checkpoint validation during session log creation.

## Scope

**In Scope**:

- Extract test functions from Validate-SessionProtocol.ps1 into SessionValidation.psm1
- Create checkpoint-specific validation functions (Test-TemplateStructure, Test-EvidenceFields, Invoke-FullValidation)
- Refactor Validate-SessionProtocol.ps1 to call module functions (maintain same interface)
- Add Pester tests for new module functions
- Verify existing Validate-SessionProtocol.Tests.ps1 still passes

**Out of Scope**:

- Changes to validation rules or requirements
- Modifications to SESSION-PROTOCOL.md template
- Integration with session-init scripts (handled in separate ticket)

## Spec References

- **Tech Plan**: spec:a8a106d4-2d31-4e19-ba45-021348587a7e/23a7f44b-69e7-4399-a164-c8eedf67b455 (Component 5: Validation Module Extensions)
- **Core Flows**: spec:a8a106d4-2d31-4e19-ba45-021348587a7e/15983562-81e6-4a00-bde0-eb5590be882a (Validation Checkpoints Specification)

## Acceptance Criteria

1. SessionValidation.psm1 exports new functions:
  - `Test-TemplateStructure` - Validates template has required sections
  - `Test-EvidenceFields` - Validates evidence fields populated correctly
  - `Invoke-FullValidation` - Runs comprehensive validation
  - `Test-RequiredSections` - Shared validation for section presence
  - `Test-TableStructure` - Shared validation for table formatting
  - `Test-PathNormalization` - Shared validation for repo-relative paths
  - `Test-CommitSHAFormat` - Shared validation for commit SHA format
  - `Test-EvidencePopulation` - Shared validation for evidence fields
2. Validate-SessionProtocol.ps1 refactored to call module functions while maintaining same interface (parameters, exit codes, output format)
3. Pester tests added:
  - `scripts/modules/SessionValidation.Tests.ps1` extended with tests for new functions
  - All tests pass with 80%+ code coverage
  - Existing `scripts/tests/Validate-SessionProtocol.Tests.ps1` still passes
4. Backward compatibility verified:
  - Existing callers of Validate-SessionProtocol.ps1 continue to work
  - No breaking changes to validation behavior
  - Same exit codes and error messages

## Dependencies

None. This is a foundational refactoring that other tickets depend on.

## Implementation Notes

**Refactoring Strategy** (from Tech Plan):

1. Create new functions in SessionValidation.psm1
2. Refactor Validate-SessionProtocol.ps1 to call module functions
3. Add Pester tests for new module functions
4. Verify existing tests still pass
5. Update Phase 2 script to call checkpoint functions directly (separate ticket)

**Validation Checkpoint Contracts**:

```powershell
# Checkpoint 1: Template Structure
Test-TemplateStructure -Template $template
# Returns: @{ IsValid, Errors, Warnings }

# Checkpoint 2: Evidence Fields
Test-EvidenceFields -SessionLog $sessionLog -GitInfo $gitInfo
# Returns: @{ IsValid, Errors, Warnings, FixableIssues }

# Checkpoint 3: Full Validation
Invoke-FullValidation -SessionLogPath $path -RepoRoot $repoRoot
# Returns: @{ IsValid, Errors, Warnings }
```


