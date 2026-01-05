# Session 316: Validate-SessionProtocol Enhancements (Review Feedback)

**Date**: 2026-01-05
**Branch**: feat/session-protocol-validator-enhancements
**PR**: TBD (new feature)

## Session Start

| Requirement | Status | Evidence |
|------------|--------|----------|
| Initialize Serena | ✅ | `mcp__serena__initial_instructions` called |
| Read HANDOFF.md | ✅ | Read `.agents/HANDOFF.md` |
| Create session log | ✅ | This file |
| Read memory-index | ⏳ | In progress |
| Read relevant memories | ⏳ | In progress |
| Verify branch | ✅ | `feat/session-protocol-validator-enhancements` |

**Starting Commit**: `7bc30af0` (main HEAD after merge of PR #790)

## Objectives

Implement 4 verification comments from PR #790 Round 3 review:

1. **Comment 1**: Add table extraction and checklist validation in `Validate-SessionProtocol.ps1`
2. **Comment 2**: Port ADR-007 memory evidence validation
3. **Comment 3**: Port QA skip rules, pre-commit mode, branch and commit validation
4. **Comment 4**: Add comprehensive Pester tests for all ported features

## Context

Review feedback from PR #790 identified gaps in `Validate-SessionProtocol.ps1` that need to be addressed. These enhancements will:
1. Enforce canonical checklist templates from SESSION-PROTOCOL.md
2. Validate memory evidence per ADR-007
3. Port session-end validation logic from `Validate-Session.ps1` (QA skip rules, pre-commit mode, commit validation)
4. Add comprehensive test coverage for all features

## Relevant Memories

- `usage-mandatory`: Skill-first pattern enforcement (✅ read)
- `pester-testing-test-first`: Test-driven development pattern
- `powershell-testing-patterns`: PowerShell testing best practices
- `protocol-template-enforcement`: Session protocol template validation

## Implementation Plan

1. Read relevant memories for testing and validation patterns
2. Review current `Validate-SessionProtocol.ps1` structure
3. Review `Validate-Session.ps1` for features to port
4. Implement Comment 1: Table extraction and template validation
5. Implement Comment 2: Memory evidence validation
6. Implement Comment 3: QA skip rules and commit validation
7. Implement Comment 4: Comprehensive test coverage
8. Run tests and validate implementation

## Progress

### Test Suite Created
Added comprehensive tests to `scripts/tests/Validate-SessionProtocol.Tests.ps1`:
- **Comment 1 Tests**: Get-HeadingTable, Parse-ChecklistTable, Normalize-Step, template row-order validation
- **Comment 2 Tests**: Test-MemoryEvidence with placeholder detection, file existence validation
- **Comment 3 Tests**: Pre-commit mode, Is-DocsOnly, Test-InvestigationOnlyEligibility, Get-ImplementationFiles, branch/commit validation
- **Total New Tests**: ~40 test cases across 14 Describe blocks

### Implementation Plan
Port features from `Validate-Session.ps1` to `Validate-SessionProtocol.ps1`:

1. **Helper Functions** (lines 80-133 from Validate-Session.ps1):
   - Get-HeadingTable
   - Parse-ChecklistTable
   - Normalize-Step

2. **Memory Evidence Validation** (lines 254-353):
   - Test-MemoryEvidence function
   - Integration into Session Start validation

3. **QA Skip Rules & Commit Validation** (lines 411-707):
   - Is-DocsOnly
   - Test-InvestigationOnlyEligibility
   - Get-ImplementationFiles
   - Branch name validation
   - Commit SHA validation
   - Starting commit validation
   - Session log change validation

4. **Parameter Addition**:
   - Add -PreCommit switch parameter
   - Conditional logic for pre-commit mode

### Current Status
- ✅ Tests created (Comment 4) - 40 test cases added
- ✅ Helper functions implemented (Comments 1-3):
  - Get-HeadingTable, Parse-ChecklistTable, Normalize-Step
  - Test-MemoryEvidence with ADR-007 validation
  - Is-DocsOnly, Test-InvestigationOnlyEligibility, Get-ImplementationFiles
  - Investigation allowlist and audit artifacts patterns
- ✅ PreCommit parameter added
- ⏳ Integration into validation workflow in progress

### Implementation Complete (Helper Functions)
All required helper functions from `Validate-Session.ps1` have been ported:
- **Lines added**: ~200 lines of validated helper code
- **Functions**: 7 new helper functions
- **Script variables**: Investigation allowlist + audit artifacts patterns

### Remaining Work
Integration into `Invoke-SessionValidation` function:
1. Load SESSION-PROTOCOL.md template
2. Extract and parse tables from both protocol and session log
3. Validate exact row-order match between session and protocol
4. Call Test-MemoryEvidence for Session Start validation
5. Add QA skip rules logic
6. Add branch name validation
7. Add commit SHA validation
