# Testing Anti-Patterns

**Created**: 2026-02-07
**Source**: Issue #749 (Evidence-Based Testing Philosophy)
**References**: Dan North, Rico Mariani, `.agents/analysis/testing-coverage-philosophy.md`

---

## Anti-Pattern 1: Coverage Theater

**Description**: Writing tests to increase coverage metrics without increasing stakeholder confidence. Tests execute code paths but verify nothing meaningful.

**Detection**:
- Tests with no assertions beyond "did not throw"
- Tests that mirror implementation logic (tautological tests)
- Coverage jumps without corresponding confidence increase
- Tests for trivial getters/setters on internal types

**Correction**:
- Ask: "What stakeholder concern does this test address?"
- Each test should verify observable behavior, not implementation details
- Remove tests that produce no evidence of correctness

---

## Anti-Pattern 2: Brittle Mocks for Impossible Scenarios

**Description**: Creating elaborate mock setups for scenarios that cannot occur in production. These tests break on refactoring without catching real bugs.

**Detection**:
- Mock setup exceeds 10 lines for a single test
- Mocking internal implementation details instead of boundaries
- Tests that break on any refactoring (even behavior-preserving)
- Mocking value objects or simple data structures

**Correction**:
- Mock only at system boundaries (external APIs, file systems, databases)
- Use real objects for internal collaborators when feasible
- Prefer integration tests over heavily-mocked unit tests

---

## Anti-Pattern 3: Unit Tests as Only Testing

**Description**: Relying exclusively on unit tests while ignoring integration, end-to-end, and security testing. Even 100% unit coverage leaves gaps.

**Detection**:
- No integration tests for multi-component workflows
- Security-critical paths tested only at unit level
- No tests that exercise real file I/O, process execution, or network calls
- Test suite passes but manual testing reveals failures

**Correction**:
- Add integration tests for critical workflows (pre-commit hooks, validation pipelines)
- Security-critical code needs tests that exercise real I/O paths
- Use Pester's `-Tag` system to separate unit from integration tests
- Run integration tests in CI with appropriate isolation

---

## Anti-Pattern 4: Quality Ignored for Quantity

**Description**: Prioritizing test count or coverage percentage over test quality. Produces large test suites that are expensive to maintain but provide weak evidence.

**Detection**:
- Test suite takes long to run but catches few regressions
- Frequent test failures unrelated to code changes (flaky tests)
- High maintenance burden relative to bugs caught
- Test names describe implementation, not behavior ("test_line_42_branch")

**Correction**:
- Name tests by behavior: "rejects_paths_outside_sessions_directory"
- Delete flaky tests or fix their root cause (no skip/retry workarounds)
- Measure defect escape rate, not just coverage percentage
- One strong test beats five weak tests

---

## Anti-Pattern 5: Testing After the Fact

**Description**: Writing all tests after implementation is complete. Tests become confirmation of existing behavior rather than specification of intended behavior.

**Detection**:
- Tests written in a separate "add tests" commit after feature merge
- Tests that pass on first run without any code changes needed
- No test failures during development cycle

**Correction**:
- Write test first for security-critical code (TDD as design tool)
- For other code, write tests alongside implementation, not after
- A test that never failed during development may not be testing anything

---

## Coverage Targets by Risk Tier

| Code Category | Target | Rationale |
|---------------|--------|-----------|
| Security-critical | 100% | Attackers target untested paths (Rico Mariani). Includes: secret handling, input validation, command execution, path sanitization, auth checks |
| Business logic | 80% | Pragmatic target aligned with diminishing returns research. Covers parsing, orchestration, non-sensitive utilities |
| Read-only/docs | 60-70% | Low-risk code where test effort outweighs defect prevention value |

---

## Related Documents

- `.agents/analysis/testing-coverage-philosophy.md` (full research)
- `.agents/governance/test-location-standards.md` (where tests live)
- Serena memory: `testing-004-coverage-pragmatism`
