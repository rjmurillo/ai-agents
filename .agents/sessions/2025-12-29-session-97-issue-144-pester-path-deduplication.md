# Session 97: Issue #144 - Eliminate Path List Duplication in pester-tests.yml

**Date**: 2025-12-29
**Issue**: #144
**Branch**: refactor/144-pester-path-deduplication
**Type**: Refactoring

## Session Start Checklist

| Req | Step | Status |
|-----|------|--------|
| MUST | Serena initial_instructions | COMPLETE |
| MUST | Read .agents/HANDOFF.md | COMPLETE |
| MUST | Create session log | COMPLETE |
| MUST | List skills | COMPLETE |
| MUST | Read skill-usage-mandatory memory | COMPLETE |
| MUST | Read PROJECT-CONSTRAINTS.md | COMPLETE |

## Objective

Eliminate path list duplication in `.github/workflows/pester-tests.yml` where testable paths are defined in two locations:

1. dorny/paths-filter configuration (lines 57-66)
2. Echo output in skip-tests job (lines 138-145)

## Analysis

### Current Duplication

**paths-filter (lines 57-66)**:

```yaml
testable:
  - 'scripts/**'
  - 'build/**'
  - '.github/scripts/**'
  - '.github/tests/**'
  - '.github/workflows/pester-tests.yml'
  - '.claude/skills/**'
  - 'tests/**'
  - '.baseline/**'
```

**skip-tests echo (lines 138-145)**:

```bash
echo "  - scripts/**"
echo "  - build/**"
echo "  - .github/scripts/**"
echo "  - .github/tests/**"
echo "  - .github/workflows/pester-tests.yml"
echo "  - .claude/skills/**"
echo "  - tests/**"
echo "  - .baseline/**"
```

### Solution Approach

YAML anchors cannot be used across jobs in GitHub Actions workflows. Options:

1. **Composite Action**: Extract to a shared action that outputs the path list
2. **Reusable Workflow Output**: Pass paths as output from check-paths job
3. **Environment File**: Write paths to file and read in skip-tests
4. **Remove Echo Duplication**: Simply reference the workflow header comment

Given ADR-006 (thin workflows), the simplest solution is to output the paths from the check-paths job as a JSON array, then iterate over them in the skip-tests job.

## Progress

- [ ] Assign issue to self
- [ ] Create branch
- [ ] Implement deduplication
- [ ] Test workflow functionality
- [ ] Route to critic
- [ ] Route to QA
- [ ] Open PR

## Decisions

TBD

## Outcomes

TBD

## Session End Checklist

| Req | Step | Status |
|-----|------|--------|
| MUST | Complete session log | PENDING |
| MUST | Update Serena memory | PENDING |
| MUST | Run markdownlint | PENDING |
| MUST | Commit all changes | PENDING |
| MUST NOT | Update HANDOFF.md | N/A |
