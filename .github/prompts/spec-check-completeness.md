# Implementation Completeness Check

You are validating that the implementation satisfies all acceptance criteria from the specification.

## Task

1. Extract all acceptance criteria from the specification
2. Check if the implementation satisfies each criterion
3. Identify any missing functionality or edge cases

## Acceptance Criteria Sources

Look for acceptance criteria in:

- Explicit "Acceptance Criteria" sections
- "Given/When/Then" scenarios
- "Done Definition" or "Definition of Done"
- Numbered requirements with measurable outcomes
- Test cases or test scenarios

## Evaluation Guidelines

For each acceptance criterion, assess:

1. **Functionality**: Does the code implement the required behavior?
2. **Edge Cases**: Are boundary conditions handled?
3. **Error Handling**: Are failure scenarios addressed?
4. **Integration**: Does it work with existing code?

## Output Format

Output your analysis in this format:

```markdown
### Acceptance Criteria Checklist

- [x] Criterion 1: [description] - SATISFIED
  - Evidence: [file:line or description]
- [ ] Criterion 2: [description] - NOT SATISFIED
  - Missing: [what's needed]
- [~] Criterion 3: [description] - PARTIALLY SATISFIED
  - Implemented: [what's done]
  - Missing: [what's needed]

### Missing Functionality

1. [Specific missing feature or behavior]
2. [Edge case not handled]

### Edge Cases Not Covered

1. [Boundary condition]
2. [Error scenario]

### Implementation Quality

- **Completeness**: X% of acceptance criteria satisfied
- **Quality**: [assessment of implementation quality]

VERDICT: PASS
MESSAGE: [Brief explanation]
```

**IMPORTANT**: Output exactly `VERDICT: PASS`, `VERDICT: PARTIAL`, or `VERDICT: FAIL` (no brackets).

## Verdict Guidelines

- `PASS`: All acceptance criteria satisfied, no critical gaps
- `PARTIAL`: Most criteria satisfied but minor gaps exist
- `FAIL`: Critical acceptance criteria not satisfied
