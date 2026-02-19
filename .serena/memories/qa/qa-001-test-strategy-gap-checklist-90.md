# Qa: Test Strategy Gap Checklist 90

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

## Related

- [qa-002-qa-agent-routing-decision-85](qa-002-qa-agent-routing-decision-85.md)
- [qa-007-worktree-isolation-verification](qa-007-worktree-isolation-verification.md)
- [qa-benchmark-script-validation](qa-benchmark-script-validation.md)
- [qa-session-protocol-validation-patterns](qa-session-protocol-validation-patterns.md)
- [qa-workflow-refactoring-patterns](qa-workflow-refactoring-patterns.md)
