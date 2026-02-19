# Skill-Analysis-003: Related Issue Discovery Before Planning

**Statement**: Before planning a fix, search for related open issues that address the same root cause

**Context**: When investigating bugs or planning implementations

**Trigger**: After RCA completion, before creating implementation plan

**Evidence**: Session 04 - Issue #338 (retry logic) discovered as prerequisite for #357 (aggregation) during search

**Atomicity**: 85%

**Tag**: helpful

**Impact**: 8/10

**Created**: 2025-12-24

**Validated**: 1

**Category**: Analysis

## Search Pattern

```bash
# Search for related issues by topic keywords
gh issue list --state open --search "[topic keywords from RCA]"

# Example from Session 04
gh issue list --state open --search "copilot retry infrastructure"
# Found: #338 (retry logic) - prerequisite for #357
```

## Why This Matters

**Without Search (Anti-pattern)**:
- Duplicate work (two issues solving same problem)
- Missed dependencies (solve A before B)
- Incomplete fixes (partial solution to systemic issue)

**With Search (Correct Pattern)**:
- Discover dependencies early
- Prevent duplicate work
- Identify systemic patterns

## When to Apply

BEFORE:
- Creating implementation plan
- Starting code changes
- Designing fixes

AFTER:
- Completing RCA
- Identifying root cause
- Understanding failure modes

## Example: Session 04

```text
Original Issue: #357 (aggregation failures)
RCA Finding: Infrastructure failures + code quality failures mixed
Related Issue Search: "copilot retry infrastructure"
Discovery: #338 already addresses infrastructure retry logic
Outcome: Reference #338 in plan, avoid duplication
```

## Success Criteria

- Zero duplicate issues created
- Dependencies identified early
- Cross-references established
- Systemic patterns recognized

## Related Skills

- skill-analysis-002-rca-before-implementation: RCA precedes planning
- github-issue-assignment: Claim ownership of discovered issues

## Related

- [analysis-001-comprehensive-analysis-standard](analysis-001-comprehensive-analysis-standard.md)
- [analysis-002-rca-before-implementation](analysis-002-rca-before-implementation.md)
- [analysis-004-verify-codebase-state](analysis-004-verify-codebase-state.md)
- [analysis-comprehensive-standard](analysis-comprehensive-standard.md)
- [analysis-gap-template](analysis-gap-template.md)
