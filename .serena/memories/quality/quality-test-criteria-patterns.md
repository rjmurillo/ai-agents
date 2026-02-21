# Test Quality Criteria Patterns

**Statement**: Tests must verify actual behavior, not code structure. Pattern-matching tests are insufficient.

**Context**: QA agent reviewing test implementations

**Evidence**: PR #147 had 60 tests using `Should -Match` on script content. Issue #157 enhanced QA agent prompt with explicit criteria.

**Atomicity**: 95%

**Impact**: 9/10

## Insufficient Test Patterns (CRITICAL_FAIL)

| Pattern | Detection | Why Insufficient |
|---------|-----------|------------------|
| `Should -Match` on script content | Search for `Should -Match`, `Select-String` | Tests code structure, not behavior |
| Regex validation of code blocks | `Get-Content.*Should` without function call | Verifies syntax, not correctness |
| AAA pattern claims without execution | Arrange/Act steps missing | Structure without substance |
| Missing Mock blocks | gh CLI, API calls unmocked | External calls leak into tests |
| File existence only | Content not validated | Presence is not correctness |

## Required Test Patterns (PASS)

| Requirement | Verification | Example |
|-------------|--------------|---------|
| Function execution | Test calls the function under test | `$result = Get-Something` |
| Mock isolation | External dependencies mocked | `Mock gh { ... }` |
| Output validation | Return values checked | `$result \| Should -Be $expected` |
| Error conditions | Exception paths tested | `{ Bad-Input } \| Should -Throw` |
| Edge cases | Boundary values covered | null, empty, max values |

## Test Review Checklist

```markdown
- [ ] Tests execute the code under test (not just inspect it)
- [ ] All external dependencies (gh CLI, APIs, filesystem) are mocked
- [ ] Tests verify outputs match expected values
- [ ] Error conditions are tested with negative tests
- [ ] Edge cases are covered (null inputs, empty arrays, boundary values)
- [ ] Test names describe the scenario being tested
- [ ] No tests use pattern matching on source code as validation
```

## Evidence Template for Flagging

```markdown
## Insufficient Test Evidence

| Test File | Test Name | Anti-Pattern | Line Reference |
|-----------|-----------|--------------|----------------|
| [File] | [Name] | Pattern-match without execution | [File:Line] |

**Verdict**: CRITICAL_FAIL
**Reason**: [N] tests verify code structure instead of behavior
**Required Fix**: Rewrite tests to execute functions and validate outputs
```

## Related

- Issue #157: Enhance QA agent prompt with test quality criteria
- PR #147: Pattern-based tests correctly flagged but needed more specific guidance
- PR #1234: Implementation of test quality criteria section
- [quality-qa-routing](quality-qa-routing.md): When to invoke QA agent
