# Plan Critique: ADR-017 Domain Index Format Validation Amendment

## Verdict

**NEEDS REVISION**

## Summary

The amendment correctly identifies the requirement but the validation mechanism described is **incorrect**. The current `Validate-MemoryIndex.ps1` script does NOT enforce "pure lookup table" format and CANNOT detect prohibited elements (titles, metadata, prose, navigation sections).

## Strengths

1. **Requirement is clear**: The prohibited elements list is comprehensive and actionable
2. **Rationale is sound**: Token efficiency justification aligns with ADR-017 core objectives
3. **Placement is appropriate**: Confirmation section is correct location for validation requirements
4. **Format specification**: The allowed format is precisely defined with example

## Issues Found

### Critical (Must Fix)

- [ ] **Line 227: Validation mechanism claim is false**
  - **Current text**: "Validation mechanism: `Validate-MemoryIndex.ps1` MUST reject index files containing prohibited elements."
  - **Reality**: Script only validates:
    1. File references exist (line 146-176)
    2. Keyword density ≥40% (line 178-247)
    3. Memory-index references domain indices (line 306-339)
    4. Orphaned files detection (line 249-304)
  - **Evidence**: `Get-IndexEntries` function (lines 98-144) parses table rows but does NOT validate format purity. It extracts `| keywords | file |` patterns without rejecting non-table content.
  - **Impact**: Amendment claims validation exists when it does not. This creates false confidence and allows format violations to pass CI checks.

### Important (Should Fix)

- [ ] **Line 206-230: Amendment section placement**
  - **Current**: Section titled "Domain Index Format Validation" appears as subsection under "Confirmation"
  - **Issue**: This is a **new requirement**, not a confirmation mechanism
  - **Recommendation**: Move to "Validation Checklist" (line 332-341) and add corresponding test to confirmation mechanisms

- [ ] **Missing implementation plan**
  - The amendment describes the requirement but provides no roadmap for implementing the validation logic
  - **Recommendation**: Add to "Confirmation" (line 198-230) or reference blocking issue:
    - "Validation mechanism pending: Issue #XXX tracks implementation of format validation in `Validate-MemoryIndex.ps1`"

### Minor (Consider)

- [ ] **Line 225: Rationale redundancy**
  - Text repeats token efficiency rationale already established in ADR body (lines 30-31, 123-133)
  - **Suggestion**: Reduce to single sentence: "Rationale: Frequent loading during retrieval makes non-lookup content costly."

## Questions for Amendment Author

1. **Validation implementation**: Should this amendment be marked as "Proposed" until validation logic is implemented?
2. **Blocking status**: Line 229 states "Blocking for Phase 3+ rollout" - does this mean Phase 3 cannot proceed until validation exists?
3. **Enforcement priority**: Is this a hard blocker or a best-practice guideline?

## Recommendations

### Option 1: Mark as Aspirational (Recommended)

Rewrite lines 227-229:

```markdown
**Validation mechanism (not yet implemented)**: Future enhancement to `Validate-MemoryIndex.ps1` will reject index files containing prohibited elements.

**Implementation tracking**: Issue #XXX

**Blocking for Phase 3+ rollout**: Validation enforcement required before expanding tiered architecture to additional domains.
```

### Option 2: Implement Validation First

1. Create validation logic in `Validate-MemoryIndex.ps1`:
   - Add `Test-IndexFormat` function that checks for prohibited elements
   - Integrate into `Invoke-MemoryIndexValidation` pipeline
2. Test against existing domain indices (copilot, coderabbit)
3. Update amendment to reference implemented validation
4. Add to CI workflow validation checklist

### Option 3: Demote to Guideline

Remove validation claim and convert to style guideline:

```markdown
**Format guideline**: Domain index files SHOULD contain only the keywords table. Titles, metadata, prose, and navigation sections inflate context window usage without aiding retrieval.

**Enforcement**: Manual review during PR approval.
```

## Approval Conditions

Amendment cannot be approved until ONE of the following:

1. **Validation claim removed** and marked as future enhancement (Option 1)
2. **Validation implemented** and tested (Option 2)
3. **Requirement demoted** to guideline with manual enforcement (Option 3)

## Technical Analysis

### Current Parser Behavior

`Get-IndexEntries` (lines 98-144) uses regex `^\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|$` to extract table rows. This pattern:

- **Matches**: Any line with two pipe-separated cells
- **Ignores**: All non-table content (titles, prose, metadata)
- **Result**: Script silently **accepts** files with prohibited elements

### Example: Format Violation Undetected

```markdown
# Skills Index - Copilot Domain

**Last Updated**: 2025-12-28

This index provides keyword-based routing to Copilot-related skills.

| Keywords | File |
|----------|------|
| P0 P1 P2 | copilot-platform-priority |
```

**Current behavior**: Script extracts the table row successfully, **PASS** validation
**Expected behavior (per amendment)**: Script should **FAIL** validation due to title, metadata, and prose

### Implementation Complexity

Adding format validation requires:

1. **Negative detection**: Scan for prohibited patterns before table parsing
2. **Regex patterns**:
   - Title: `^#\s+`
   - Metadata: `^\*\*[^*]+\*\*:\s+`
   - Navigation: `^##\s+Index` or `Parent:\s+`
   - Prose: Any line not matching table pattern or blank
3. **Error reporting**: Specify line number and violation type
4. **Estimated effort**: 2-4 hours (implementation + testing)

## Recommendation

**Return to planner** to clarify validation requirement status and update amendment per Option 1 (mark as aspirational) or initiate implementation tracking issue for validation logic.

## Impact Analysis Review

Not applicable (no specialist consultations for amendment).

## Handoff

Amendment needs revision to align validation claims with current script capabilities. Recommend orchestrator routes to:

- **planner**: If amendment should be reworded to reflect aspirational validation
- **implementer**: If validation logic should be implemented before amendment approval
