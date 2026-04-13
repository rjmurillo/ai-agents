# QA Agent Routing Skills

**Statement**: MUST route to qa agent after feature implementation before commit

**Context**: After feature implementation, before git commit

**Evidence**: PR #60 skipped qa, vulnerability not caught until PR #211

**Atomicity**: 90%

**Impact**: 8/10

## BLOCKING Gate Pattern

```markdown
## Phase X: QA Validation (BLOCKING)

You MUST route to qa agent after feature implementation:

Task(subagent_type="qa", prompt="Validate [feature]")

**Verification**: QA report exists in `.agents/qa/`

**If skipped**: Untested code may contain bugs or vulnerabilities
```

## Test Strategy Gap Checklist

- [ ] Cross-platform consistency tests
- [ ] Negative tests (invalid inputs, error conditions)
- [ ] Edge cases (boundary values, empty/null)
- [ ] Error handling tests (exception paths)
- [ ] Performance tests (if applicable)

## When QA Agent is MANDATORY

- New features
- Complex logic
- Cross-platform concerns
- Security-sensitive code
- Breaking changes

## When to Skip (exceptions)

- Coverage >80% with edge cases
- All tests passing
- Change is trivial (docs, comments, formatting)

## Anti-Pattern

Skipping qa because "tests look good" (subjective)

## Related

- [quality-agent-remediation](quality-agent-remediation.md)
- [quality-basic-testing](quality-basic-testing.md)
- [quality-critique-escalation](quality-critique-escalation.md)
- [quality-definition-of-done](quality-definition-of-done.md)
- [quality-prompt-engineering-gates](quality-prompt-engineering-gates.md)
