# Skill-Test-Pester-005: Test-First Development

**Statement**: Create Pester tests during implementation (not after) to validate correctness before commit, achieving 100% pass rates.

**Context**: During implementation phase for PowerShell scripts/modules.

**Evidence**: Session 21 created 13 tests alongside Check-SkillExists.ps1 → 100% pass rate on first run.

**Atomicity**: 95%

**Impact**: 8/10

## Pattern

Write test → Write code → Run test → Refactor → Commit (all tests passing)

## Evidence Details

- 13 Pester tests created alongside implementation
- All operations tested: pr, issue, reactions, label, milestone
- Parameters tested: -Operation, -Action, -ListAvailable
- 100% pass rate on first run (13/13 passed, 0 failed)

## Anti-Pattern

Writing tests after implementation claims completion.

## Benefits

- Validates implementation correctness during development
- Catches bugs before commit
- Higher confidence in code quality
- Reduces fix commits after merge
