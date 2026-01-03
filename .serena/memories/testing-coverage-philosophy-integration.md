# Testing Coverage Philosophy Integration

## Core Insight

Testing should increase stakeholder confidence through evidence (Dan North), not chase coverage metrics. Two perspectives reconcile based on risk profile: Rico Mariani's 100% block coverage minimum applies to high-security/privacy systems under attack; industry consensus (60-80%) applies to typical software including ai-agents.

## Key Principles

1. **Evidence over metrics** (Dan North): Testing if and only if it increases confidence for stakeholders through incontrovertible data
2. **100% is ante, not end goal** (Rico Mariani): Unit coverage is baseline for "acceptance testing," not comprehensive testing
3. **Diminishing returns context-dependent**: True for typical software; false for high-security systems with sanitizers
4. **Quality over quantity**: 80% with thoughtful tests beats 95% with brittle tests

## Application to ai-agents

**Risk Profile**: HIGH-SECURITY (adversarial environment) - prompt injection, secret disclosure, ability abuse, open source exposure. No sanitizer infrastructure in PowerShell/Pester.

**Revised Tiered Coverage Targets** (Rico's security principle applies):
- **100% coverage REQUIRED**: Secret handling, input validation (user prompts, paths, commands), authorization checks, command execution (bash/PowerShell/git), path sanitization, authentication flows
- **80% coverage**: Business logic without security implications (text parsing, formatting, workflow orchestration)
- **60-70% coverage**: Read-only analysis, documentation generation
- **Skip testing**: Impossible states, dead code (delete instead)

**CRITICAL**: Most ai-agents code is security-critical (operates with GitHub credentials, file system access, untrusted prompts)

**Current Practice Validation**:
- Session 68: 69.72% coverage with comprehensive critical path testing = CORRECT (aligns with Google 60-75%)
- ADR-006 (thin workflows, testable modules) = enables high-value testing
- testing-004-coverage-pragmatism memory = existing knowledge confirmed and enhanced

## Integration Points

- **Agent**: qa agent should evaluate tests using evidence-based criteria (stakeholder confidence), not just coverage %
- **Protocol**: Add testing quality checklist to session protocol (critical paths 100%, realistic errors 80%+)
- **Memory**: Update testing-004-coverage-pragmatism with philosophical foundations
- **Skill**: Enhance Pester testing skills with test quality evaluation (not just coverage reporting)

## Practical Guidance

**Before writing a test, ask**:
1. Which stakeholder benefits from this evidence?
2. What will they know after this test?
3. What data does this produce?
4. Is this the best way to gain confidence? (If no, find better approach or skip)

**Priority-based testing**:
- Tier 1 (100%): Critical business logic, security-sensitive code, edge cases with known issues
- Tier 2 (80%+): Error handling for realistic scenarios, integration points
- Tier 3 (60-70%): Verbose logging, wrappers, configuration
- Tier 4 (skip): Impossible error states, dead code, defensive checks when impossible

**Anti-patterns to avoid**:
- Coverage theater (testing to increase metrics, not confidence)
- Brittle mocks for impossible scenarios
- Unit tests as only testing (ignoring integration/E2E)
- Test quality ignored for quantity

## References

- Analysis: .agents/analysis/testing-coverage-philosophy.md
- Dan North: https://dannorth.net/blog/we-need-to-talk-about-testing/
- Rico Mariani: https://ricomariani.medium.com/100-unit-testing-now-its-ante-f0e2384ffedf
- Related Memories: testing-004-coverage-pragmatism, ADR-006, pester-testing-cross-platform
- Forgetful Memory IDs: 70-79 (Dan North evidence-based, Rico ante, diminishing returns synthesis, priority tiers, security/privacy, coverage theater anti-pattern, ADR-006 synergy, quality over quantity, sanitizer value, stakeholder framework)

## Next Steps

1. Update testing-004-coverage-pragmatism with philosophical foundations
2. Add testing quality checklist to session protocol
3. Enhance qa agent prompt with evidence-based criteria
4. Document anti-patterns in .agents/governance/TESTING-ANTI-PATTERNS.md
