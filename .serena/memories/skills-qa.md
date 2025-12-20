# QA Skills

**Extracted**: 2025-12-16
**Source**: `.agents/qa/` directory

## Skill-QA-001: Test Strategy Gap Checklist (90%)

**Statement**: Verify test plans include cross-platform, negative, edge, error, and performance tests

**Context**: Test strategy review and QA planning

**Evidence**: Agent consolidation test strategy review identified missing categories

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 8/10

**Checklist**:

- [ ] Cross-platform consistency tests
- [ ] Negative tests (invalid inputs, error conditions)
- [ ] Edge cases (boundary values, empty/null)
- [ ] Error handling tests (exception paths)
- [ ] Performance tests (if applicable)

**Detection**: Test plan missing these categories
**Fix**: Add missing test categories before implementation

**Source**: `.agents/qa/001-agent-consolidation-test-strategy-review.md`

---

## Skill-QA-002: QA Agent Routing Decision (85%)

**Statement**: Route to qa agent after implementing features unless tests are comprehensive and passing

**Context**: After feature implementation, before commit

**Trigger**: Feature code complete

**Evidence**: Serena transformation (2025-12-17): Manual testing skipped qa agent workflow. Pattern observed in prior sessions where agents short-circuited workflow without clear criteria.

**Atomicity**: 85%

- Routing decision concept ✓
- Clear timing (after implementation) ✓
- Length: 12 words ✓
- Slightly vague "comprehensive" (-10%)

**Impact**: 7/10 - Ensures process consistency, clarifies when qa adds value

**Category**: QA Workflow

**Tag**: helpful

**Created**: 2025-12-17

**Validated**: 1 (Serena transformation pattern)

**Definition of "Comprehensive"**:

- Coverage >80%
- Multiple test cases per function
- Edge cases included
- Negative tests present
- Error handling verified

**When to Skip QA Agent** (exceptions to workflow):

- Tests are comprehensive (per definition above)
- All tests passing
- Change is trivial (docs, comments, formatting)

**When QA Agent is MANDATORY**:

- New features
- Complex logic
- Cross-platform concerns
- Security-sensitive code
- Breaking changes

---

## Related Documents

- Source: `.agents/qa/001-agent-consolidation-test-strategy-review.md`
- Source: `.agents/retrospective/2025-12-17-serena-transformation-implementation.md`
- Related: skills-validation (validation quality patterns)
- Related: skills-implementation (test discovery workflow)
