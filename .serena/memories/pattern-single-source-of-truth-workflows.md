# Pattern: Single Source of Truth in Workflows

**Date**: 2025-12-29
**Context**: Issue #144 - Path list duplication elimination
**Status**: Established Pattern

---

## Problem

Workflows often duplicate configuration in multiple locations:

- Header documentation
- Filter definitions
- Skip/echo messages

This creates maintenance burden where lists get out of sync.

## Solution Pattern

**Establish one authoritative source and reference it elsewhere.**

### Example: dorny/paths-filter

```yaml
# HEADER: Reference only
# Testable paths are defined ONCE in the check-paths job filters block.
# See the 'testable' filter for the authoritative list.

jobs:
  check-paths:
    outputs:
      testable-paths: ${{ steps.filter.outputs.testable_files }}
    steps:
      - uses: dorny/paths-filter@...
        with:
          # SINGLE SOURCE OF TRUTH: All testable paths defined here only
          # Categories: ...
          list-files: json
          filters: |
            testable:
              - 'scripts/**'
              - 'build/**'
              # ... full list

  skip-tests:
    steps:
      - run: |
          echo "See the 'testable' filter in check-paths job for paths."
          echo "Reference: .github/workflows/pester-tests.yml"
```

## Implementation Checklist

- [ ] Identify duplicated lists
- [ ] Choose authoritative source (prefer data structure over comment)
- [ ] Mark authoritative source with `# SINGLE SOURCE OF TRUTH` comment
- [ ] Replace duplicates with references to authoritative source
- [ ] If exporting as output, ensure it's consumed (or remove if unused)

## Related

- Issue #144: Pester tests path duplication
- ADR-006: Thin workflows (avoid embedding logic)
- Pattern: DRY principle in workflows

## Related

- [pattern-agent-generation-three-platforms](pattern-agent-generation-three-platforms.md)
- [pattern-github-actions-variable-evaluation](pattern-github-actions-variable-evaluation.md)
- [pattern-handoff-merge-session-histories](pattern-handoff-merge-session-histories.md)
- [pattern-thin-workflows](pattern-thin-workflows.md)
