# Skill-Testing-002: Test-First Development

## Statement

Create Pester tests during implementation (not after) to validate correctness before commit, achieving 100% pass rates

## Context

During implementation phase for PowerShell scripts/modules

## Evidence

Session 21 (2025-12-18): Created 13 tests alongside Check-SkillExists.ps1 -> 100% pass rate on first run -> high confidence before commit

## Metrics

- Atomicity: 95%
- Impact: 9/10
- Category: testing, quality, test-driven-development
- Created: 2025-12-18
- Tag: helpful
- Validated: 1

## Related Skills

- Skill-Analysis-001 (Comprehensive Analysis Standard)
- Skill-Protocol-002 (Verification-Based Gate Effectiveness)

## Test-First Development Pattern

### Pattern: Write Test -> Write Code -> Run Test -> Refactor -> Commit

**Step 1: Write Test**

```powershell
# tests/Check-SkillExists.Tests.ps1
Describe 'Check-SkillExists' {
    It 'Returns true when skill exists' {
        $result = Check-SkillExists -Operation 'pr' -Action 'create'
        $result | Should -Be $true
    }
}
```

**Step 2: Write Code (minimal to pass)**

```powershell
# scripts/Check-SkillExists.ps1
function Check-SkillExists {
    param([string]$Operation, [string]$Action)
    # Simple implementation
    return $true
}
```

**Step 3: Run Test**

```powershell
Invoke-Pester -Path tests/Check-SkillExists.Tests.ps1
# Expected: 1 passed, 0 failed
```

**Step 4: Refactor (add real logic)**

```powershell
function Check-SkillExists {
    param([string]$Operation, [string]$Action)
    # Real implementation with validation
    $skillName = "$Operation-$Action"
    return Test-Path ".serena/memories/skill-github-$skillName.md"
}
```

**Step 5: Commit (all tests passing)**

```bash
git add scripts/Check-SkillExists.ps1 tests/Check-SkillExists.Tests.ps1
git commit -m "feat(tools): add Check-SkillExists.ps1 for skill validation"
```

## Test Coverage Targets

| Coverage Type | Target | Session 21 Achieved |
|---------------|--------|---------------------|
| Operations tested | 100% | 5/5 operations (pr, issue, reactions, label, milestone) |
| Parameters tested | 100% | All params (-Operation, -Action, -ListAvailable) |
| Validation tested | 100% | ValidateSet, missing params, substring matching |
| Pass rate | 100% | 13/13 tests passed on first run |

## Anti-Pattern: Test-After Development

**Problematic sequence**:

1. Write all implementation code
2. Commit code
3. (Maybe) write tests later
4. Discover bugs in committed code

**Why it fails**: No validation before commit, bugs reach main branch

## Benefits of Test-First

1. **Confidence**: 100% pass rate before commit
2. **Design**: Tests force clear API design
3. **Coverage**: Natural coverage (tests written alongside code)
4. **Regression**: Prevent future breakage
5. **Documentation**: Tests show intended usage

## Session 21 Example

**Implementation**: Check-SkillExists.ps1 (67 lines)
**Tests**: Check-SkillExists.Tests.ps1 (13 tests)

**Tests created alongside implementation**:

- Test 1: Basic operation check (pr-create)
- Test 2: Different operation (issue-comment)
- Test 3-7: All five operations validated
- Test 8: -ListAvailable parameter
- Test 9-10: Parameter validation
- Test 11-13: Substring matching, edge cases

**Result**: 100% pass rate on first run, commit with confidence

## Success Criteria

- Tests written during implementation (not after)
- 100% pass rate before commit
- All operations, parameters, validations tested
- Test file committed alongside implementation file
- No bugs discovered in committed code
