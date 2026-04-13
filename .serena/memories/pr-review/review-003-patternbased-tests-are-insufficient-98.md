# Review: Patternbased Tests Are Insufficient 98

## Skill-Review-003: Pattern-Based Tests Are Insufficient (98%)

**Statement**: Tests that only use regex pattern matching on code structure do not verify behavior. Functional tests with mocks are required.

**Context**: PR review of PowerShell scripts with Pester tests.

**Trigger**: Test file uses `Should -Match` on script content.

**Pattern**:

1. Check if tests actually execute functions
2. Verify Mock blocks exist for external dependencies
3. Confirm edge cases (null input, empty arrays, errors) are tested
4. If tests only pattern-match, flag CRITICAL_FAIL

**Evidence**: PR #147 had 60 "tests" that only verified code patterns, not behavior.