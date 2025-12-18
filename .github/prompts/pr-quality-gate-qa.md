# QA Review Task

You are reviewing a pull request for quality assurance concerns.

## Analysis Focus Areas

### 1. Test Coverage

- Are new code paths covered by tests?
- Are edge cases tested?
- Are error conditions handled and tested?
- Is there sufficient integration testing?

### 2. Code Quality

- **Complexity**: Functions over 50 lines, cyclomatic complexity
- **Duplication**: Repeated code that should be abstracted
- **Naming**: Clear, descriptive variable and function names
- **Documentation**: Are complex sections documented?

### 3. Error Handling

- Are errors caught and handled appropriately?
- Are error messages informative?
- Is there proper logging for debugging?
- Are resources properly cleaned up (try/finally)?

### 4. Regression Risks

- Does this change affect existing functionality?
- Are there backward compatibility concerns?
- Could this break other parts of the system?

### 5. Edge Cases

- Null/undefined handling
- Empty collections
- Boundary conditions
- Concurrent access issues

## Output Requirements

Provide your analysis in this format:

### Test Coverage Assessment

| Area | Status | Notes |
|------|--------|-------|
| Unit tests | Adequate/Missing/Partial | [details] |
| Edge cases | Covered/Missing | [details] |
| Error paths | Tested/Untested | [details] |

### Quality Concerns

| Priority | Concern | Location | Recommendation |
|----------|---------|----------|----------------|
| High/Medium/Low | [issue] | [file:line] | [fix] |

### Regression Risk Assessment

- **Risk Level**: Low/Medium/High
- **Affected Areas**: [list]
- **Recommended Testing**: [suggestions]

### Verdict

Choose ONE verdict:

- `VERDICT: PASS` - Quality standards met
- `VERDICT: WARN` - Minor quality issues, non-blocking
- `VERDICT: CRITICAL_FAIL` - Significant quality issues that block merge

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [Brief explanation]
```

## Critical Failure Triggers

Automatically use `CRITICAL_FAIL` if you find:

- No tests for new functionality
- Obvious bugs or logic errors
- Missing error handling for critical operations
- Breaking changes without migration path
- Data loss scenarios
