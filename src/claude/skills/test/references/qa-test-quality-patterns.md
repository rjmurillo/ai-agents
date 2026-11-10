# Test Quality Patterns

Loaded by the `qa` agent when it reviews tests for sufficiency. The agent body keeps the Evidence for Verdict block, because its verdict wording differs by harness.

## Insufficient Test Patterns ([FAIL])

Flag tests that match these anti-patterns:

| Pattern | Why Insufficient | Evidence |
|---------|------------------|----------|
| `Should -Match` on script content | Tests code structure, not behavior | No function execution |
| Regex validation of code blocks | Verifies syntax, not correctness | Output not checked |
| AAA pattern claims without execution | Structure without substance | Arrange/Act steps missing |
| Missing Mock blocks for external deps | External calls leak into tests | gh CLI, API calls unmocked |
| Tests verifying file existence only | Presence is not correctness | Content not validated |

**Detection**: Search for `Should -Match`, `Select-String`, `Get-Content.*Should` patterns without corresponding function invocations.

## Required Test Patterns ([PASS])

Tests must demonstrate these characteristics. Each line below is valid Pester
that you can paste and run:

```powershell
# Function execution: the test calls the function under test
$result = Get-Something

# Mock isolation: external dependencies are mocked
Mock gh { '{"number":1}' }

# Output validation: return values are checked
$result | Should -Be $expected

# Error conditions: exception paths are tested
{ Bad-Input } | Should -Throw

# Edge cases: boundary values are covered (null, empty, maximum)
$null, @(), [int]::MaxValue | ForEach-Object { Get-Something $_ }
```

## Test Review Checklist

When reviewing tests, verify:

```markdown
- [ ] Tests execute the code under test (not just inspect it)
- [ ] All external dependencies (gh CLI, APIs, filesystem) are mocked
- [ ] Tests verify outputs match expected values
- [ ] Error conditions are tested with negative tests
- [ ] Edge cases are covered (null inputs, empty arrays, boundary values)
- [ ] Test names describe the scenario being tested
- [ ] No tests use pattern matching on source code as validation
```
