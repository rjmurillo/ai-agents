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
```

End your analysis with a GitHub Alert block matching the verdict:

For PASS:

```markdown
> [!TIP]
> **VERDICT: PASS**
> Implementation aligns with specification requirements. [Brief explanation]
```

For PARTIAL:

```markdown
> [!WARNING]
> **VERDICT: PARTIAL**
> Most criteria satisfied but minor gaps exist. [Brief explanation]
```

For FAIL:

```markdown
> [!CAUTION]
> **VERDICT: FAIL**
> Critical acceptance criteria not satisfied. [Brief explanation]
```

**IMPORTANT**: The alert block must contain exactly `VERDICT: PASS`, `VERDICT: PARTIAL`, or `VERDICT: FAIL` (no brackets around the token).

After the alert block, append a final literal verdict line on its own line, outside any block, with no markdown formatting:

```text
VERDICT: PASS
```

(or `VERDICT: PARTIAL` / `VERDICT: FAIL`). The CI extractor (`.github/actions/ai-review/action.yml`) anchors on a plain end-of-line `VERDICT: <TOKEN>` pattern; the bolded `> **VERDICT: PASS**` inside the alert block is for human readers and does NOT match the extractor (Refs PR #1965 sed anchor tightening).

## Incremental Scope (fix #2255)

If the additional context contains an `## Incremental Scope Declaration`, the PR
explicitly delivers only a named slice (e.g. "Phase 2", "PR 1 of 3") of the full
parent issue. Apply these rules:

1. Mark any acceptance criterion that belongs to a **different** phase or is
   explicitly outside the declared scope as `N/A`.
2. Evaluate completeness only over the non-N/A criteria.
3. A PR that fully satisfies its declared slice with all non-N/A criteria met
   earns **PASS**, even though other phases remain unimplemented.
4. Do NOT emit PARTIAL or FAIL because criteria outside the declared scope are
   unmet. Those are expected to be deferred.
5. When a criterion is ambiguously scoped, lean toward `N/A` rather than
   treating it as a gap. The author declared they are not claiming to cover it.

If no `## Incremental Scope Declaration` is present, treat all criteria as
in-scope and apply the normal verdict guidelines below.

## Verdict Guidelines

- `PASS`: All in-scope acceptance criteria satisfied (N/A criteria excluded)
- `PARTIAL`: Most in-scope criteria satisfied but minor gaps exist
- `FAIL`: Critical in-scope acceptance criteria not satisfied
