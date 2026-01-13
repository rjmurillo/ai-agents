# Skill-Testing-004: Code Coverage Pragmatism

**Statement**: Perfect 100% code coverage is often not achievable or worthwhile; focus on critical paths and realistic scenarios rather than chasing coverage metrics

**Context**: Setting test coverage targets for PowerShell scripts and modules

**Evidence**: Session 68 (2025-12-22): Generate-Skills.Tests.ps1 (script deleted in commit d7f2e08, replaced by validate-skill.py)
- Target: 100% code coverage
- Achieved: 69.72% with 60 passing tests
- All critical paths tested (YAML parsing, section extraction, frontmatter generation)
- Uncovered code: Verbose logging, minor edge cases, some error branches
- Result: High-quality, maintainable test suite despite not reaching 100%

**Atomicity**: 91%

**Tag**: helpful (testing strategy)

**Impact**: 8/10 (prevents wasted effort, focuses on value)

**Created**: 2025-12-22

**Validated**: 1 (Session 68)

**Coverage Tiers**:

| Coverage % | Focus | Typical Uncovered Code |
|------------|-------|------------------------|
| 60-70% | Happy paths, core logic | Error handling, logging, edge cases |
| 70-80% | Core + major error paths | Verbose logging, rare edge cases |
| 80-90% | Core + comprehensive errors | Defensive code, impossible states |
| 90-100% | Everything | Often requires brittle/artificial tests |

**What to prioritize** (in order):

1. **Critical business logic** (100% coverage)
   - Data transformation
   - Calculations
   - Core algorithms

2. **Error handling for realistic scenarios** (80%+ coverage)
   - Invalid input
   - Missing files
   - Network failures

3. **Edge cases with known issues** (100% coverage)
   - Boundary values
   - Empty collections
   - Null/undefined values

4. **Security-sensitive code** (100% coverage)
   - Input validation
   - Path sanitization
   - Authentication/authorization

**What NOT to chase**:

- Verbose logging statements (low risk, high effort)
- Impossible error states (can't happen in practice)
- Defensive null checks when nulls are guaranteed impossible
- Dead code branches (delete instead)

**Example** (Session 68):

```powershell
# Function tested: Normalize-Newlines (100% coverage)
# - Core transformation logic
# - Multiple input scenarios
# - Both CRLF and LF modes

# Function partially tested: Write-Log (~0% coverage)
# - Only called with -VerboseLog parameter
# - Low risk: just Write-Host wrapper
# - Not worth test complexity to mock $VerboseLog
```

**Coverage quality over quantity**:

- 70% coverage with realistic scenarios > 95% coverage with brittle mocks
- End-to-end tests often provide better value than unit test coverage
- Missing coverage in logging/diagnostics is acceptable if core logic is solid

**When to target 100%**:

1. Security-critical code
2. Financial calculations
3. Data validation/transformation
4. Public APIs with strong contracts
5. Code with history of bugs

**When 70% is fine**:

1. Scripts with extensive logging
2. Wrappers around well-tested libraries
3. Configuration/setup code
4. Diagnostic utilities

**Commit message pattern**:

```
test(module): add comprehensive tests with [X]% coverage

- [N] tests covering all major functions
- Focus areas: [critical paths listed]
- Uncovered: [low-risk items listed]
```

**Related**:
- skill-testing-002-test-first-development
- pester-test-isolation-pattern
- ADR-006: Thin Workflows, Testable Modules (move logic to modules for easier testing)

**Anti-Pattern**: Pursuing 100% coverage by testing unreachable code or adding artificial test scenarios

## Related

- [testing-002-test-first-development](testing-002-test-first-development.md)
- [testing-003-script-execution-isolation](testing-003-script-execution-isolation.md)
- [testing-007-contract-testing](testing-007-contract-testing.md)
- [testing-008-entry-point-isolation](testing-008-entry-point-isolation.md)
- [testing-coverage-philosophy-integration](testing-coverage-philosophy-integration.md)
