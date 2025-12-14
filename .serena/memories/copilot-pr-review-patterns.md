# Copilot PR Review Patterns

## Pattern: Documentation Consistency Checking

**Discovered**: 2025-12-14 on PR #25

### Behavior

Copilot cross-references inlined content against source documentation files and flags discrepancies.

### Characteristics

- Identifies when inlined content differs from source documentation
- Provides specific code suggestions for fixes
- Comments are VALID (not false positives) for consistency checking
- Multiple comments may be generated for same issue across different files

### Example from PR #25

- 9 comments generated
- 3 about missing Refactoring task type (Quick Fix)
- 6 about Security/Infrastructure sequence discrepancies (Standard - requires user decision)

### Triage Classification

| Copilot Comment Type | Likely Path | Handling |
|---------------------|-------------|----------|
| Missing table row/entry | Quick Fix | Accept suggestion |
| Content differs from source | Standard | Investigate intent, decide direction |
| Typo/formatting | Quick Fix | Accept suggestion |

## Pattern: Sequence Consistency Checking

**Discovered**: 2025-12-14 on PR #32

**Description**: Copilot identifies when documented workflows/sequences are incomplete compared to referenced content elsewhere in the same PR.

**Trigger**: Cross-references agent sequences against Phase documentation, identifies missing elements in sequences that are documented elsewhere. Comments are VALID (not false positives) for consistency. May generate multiple identical comments across different files.

**Example from PR #32**:

- 5 comments generated about missing `devops` in Ideation sequence
- All comments referenced Phase 4 which explicitly includes devops
- Same pattern repeated across orchestrator files and documentation

**Triage**:

| Copilot Comment Type | Likely Path | Handling |
|---------------------|-------------|----------|
| Missing sequence element | Quick Fix | Accept suggestion, apply across all affected files |
| Sequence differs from Phase docs | Quick Fix | Verify Phase docs are source of truth |
| Platform sync gap (review summary) | Standard | Sync content across platforms |

---

## Response Templates

**Accept suggestion**:
> Thanks @Copilot! Good catch - I'll make this update.

**Keep PR version (intentional change)**:
> @Copilot The change is intentional. I'll update the source documentation to reflect this improvement.

**Revert to source**:
> @Copilot Thanks for the consistency check. I'll update to match source documentation.
