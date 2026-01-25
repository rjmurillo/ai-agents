# Testing Exit Code Interpretation

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 1

## Purpose

Documents the correct interpretation of test framework exit codes to prevent false assumptions about test success.

## Constraints (HIGH confidence)

### pytest Exit Code Semantics

**Any non-zero count (errors OR failures) means test suite FAILED and should block commits.**

pytest output categories:
- `passed` = success (test executed and assertions passed)
- `failed` = assertion failure (test executed but assertions failed)
- `error` = test setup/collection failure (test couldn't run)

**Critical**: ALL non-pass outcomes mean the test suite did NOT pass. Exit code is non-zero.

Example interpretation:
| Output | Exit Code | Verdict | Action |
|--------|-----------|---------|--------|
| `66 passed` | 0 | PASS | Safe to commit |
| `66 passed, 1 failed` | 1 | FAIL | Fix before commit |
| `66 passed, 1 error` | 1 | FAIL | Fix before commit |
| `65 passed, 1 failed, 1 error` | 1 | FAIL | Fix before commit |

(Session 2026-01-18, PR #967)

### Process Requirement

**Run full test suite before EVERY commit/push. Verify exit code 0.**

If ANY errors or failures appear in output:
1. STOP - do not commit
2. Investigate the error/failure
3. Fix the issue
4. Re-run tests
5. Only commit when exit code is 0

(Session 2026-01-18, PR #967)

## Rationale

The directive "Exit code 0 (PASS) required before claiming completion" (CRITICAL-CONTEXT.md) already covers this, but the interpretation was ambiguous. This memory clarifies:

- "Exit code 0" means zero errors AND zero failures
- pytest's distinction between "error" and "failed" is internal categorization
- Both result in non-zero exit codes
- Both should block commits

## Anti-Pattern Detected

**Wrong interpretation**: Treating "error" as different from "failed" and assuming "66 passed, 1 error" is acceptable.

**Correct interpretation**: Any non-pass outcome is a test suite failure requiring investigation before commit.

## Applies To

- pytest (Python)
- Pester (PowerShell) - same principle: any non-pass = failure
- All test frameworks - exit code 0 is the universal "all tests passed" signal

## Related

- [testing-002-test-first-development](testing-002-test-first-development.md)
- [testing-003-script-execution-isolation](testing-003-script-execution-isolation.md)
- [testing-004-coverage-pragmatism](testing-004-coverage-pragmatism.md)
- [testing-007-contract-testing](testing-007-contract-testing.md)
- [testing-008-entry-point-isolation](testing-008-entry-point-isolation.md)
