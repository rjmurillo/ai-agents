---
applyTo: "tests/**,**/*.Tests.ps1,**/tests/**,.claude/skills/**/tests/**,.agents/security/benchmarks/**"
priority: high
---

# Test File Rules

Tests under `tests/`, skill `tests/` directories, and `.agents/security/benchmarks/` enforce correctness and catch regressions. They are not decoration.

## MUST

1. **Structural validation** — Quality-gate prompt tests MUST comply with ADR-023 structural requirements. Other tests follow the placement and coverage rules below.
2. **Pester version** — PowerShell tests MUST target Pester 5.7.1+. Python tests MUST target pytest 8+.
3. **Evidence for fixture changes** — MUST NOT modify baseline fixtures to make failing tests pass. A baseline change MUST cite the behavior change that justifies it.
4. **Coverage targets** — Coverage MUST meet category minimums (`AGENTS.md`): 100% security, 80% business, 60% docs.
5. **Independent tests** — Each test MUST pass in isolation. Shared mutable state is prohibited.
6. **Placement** — New tests MUST live in the canonical locations: `tests/`, `.claude/skills/<name>/tests/`, or `.agents/security/benchmarks/`.

## SHOULD

1. **AAA pattern** — SHOULD follow Arrange / Act / Assert structure for readability.
2. **Descriptive names** — `Describe` / `Context` / `It` (Pester) and test function names SHOULD describe the behavior under test, not the implementation.
3. **Mock at boundaries** — SHOULD mock external dependencies (HTTP, filesystem, shells); avoid mocking domain logic.

## MUST NOT

1. MUST NOT rename a test to silence a failure.
2. MUST NOT add `Skip` / `@pytest.mark.skip` without a linked issue tracking re-enablement.
3. MUST NOT suppress protocol validation in tests (investigation exemption is narrow; see ADR-034).

## References

- `.agents/architecture/ADR-023-quality-gate-prompt-testing.md` — structural contract
- `.agents/architecture/ADR-034-investigation-session-qa-exemption.md` — narrow skip policy
- `.agents/steering/testing-approach.md` — Pester patterns and anti-patterns
- `.agents/governance/TESTING-ANTI-PATTERNS.md` — forbidden patterns
