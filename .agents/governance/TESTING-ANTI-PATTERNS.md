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

## Anti-Pattern 6: Stale Contract Tests

**Description**: Tests that assert an old contract (signature, return shape, error message) after the contract changed. They still pass because the old behavior is preserved or the assertions are loose enough to match both shapes. They prove nothing about the new contract surface.

**Detection**:
- A PR changes a function signature, return type, or error shape
- No test in the same diff updates assertions for the changed function
- Loose assertions (truthiness, `is not None`) instead of shape-specific ones

**Correction**:
- Apply the mirror obligation in `TESTING-RIGOR.md`: grep for tests asserting the old contract and flip them in the same diff
- Tighten assertions to the new shape, not just truthiness

**Related**: `TESTING-RIGOR.md` Contract Changes: Flip the Stale Tests section

---

## Anti-Pattern 7: A Totalizing Fallback That Erases Its Own Special Cases

**Description**: A lookup gains a catch-all fallback so no input can crash it. The fallback returns the same observable result as one of the specific entries beside it. From that moment the specific entry is behaviorally dead: adding it and deleting it produce identical output, so no test can tell them apart, and any test named for it passes whether or not the entry exists.

Defensive programming asks for the fallback. Nothing warns you that it just made a neighbor untestable. The tension is real and the entry is not redundant, because a decided mapping and an unrecognized token mean different things to a maintainer even when they mean the same thing to the caller.

**Detection**:

- A `dict.get(key, DEFAULT)` or `if key not in KNOWN: key = DEFAULT` where `DEFAULT` equals the value of an existing entry
- A test named for a specific case that still passes after you delete that case from the table
- A table entry whose only justification in review was "it is clearer to be explicit"
- The mapping and the fallback agree on the value, so the fallback silently absorbs the case

The cheap check is one command: delete the entry and rerun the suite. If it stays green, the entry has no test, and the test you thought covered it is covering the fallback.

**Correction**:

Do not delete the fallback and do not delete the entry. Make the two paths observably different, then assert on the difference.

The natural discriminator is diagnostics, and it is the one you want anyway. A decided mapping is a settled question and stays silent. An unrecognized token is a gap in the table, so the fallback says so on stderr. That asymmetry is a real requirement rather than a testing device: without it, the next producer that grows a verdict the adapter never learned drifts in unnoticed, which is the failure the fallback was added to contain.

Measured on `agent_signal` in `scripts/quality_gate/external_signal_gate.py` (issue #4487). `DID_NOT_RUN` maps to `UNKNOWN`, and the fallback also yields `UNKNOWN`. With both paths silent, deleting the alias entry left all tests green. After splitting them so the alias returns quietly and the fallback warns, deleting the entry fails exactly one test, `test_did_not_run_is_aliased_not_merely_caught_by_the_fallback`, on the presence of the warning, at 1 failed and 41 passed. Same code path, same return value, now falsifiable.

Where a warning is genuinely wrong, the other discriminators are a counter or a structured result that names which branch produced the value. Asserting on the return value alone is what does not work.

**Related**: `.claude/rules/testing.md` SHOULD 11 (catch-all fallback), added in the same change; `TESTING-RIGOR.md` positive/negative/edge requirement

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
