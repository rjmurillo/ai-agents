# GitHub Actions Labeler Skills - Extraction Summary

**Date**: 2025-12-21
**Source**: PR #226, PR #229 (hotfix)
**Evidence**: Multiple PR failures → working solution
**Quality**: High (validated through production use)

---

## Executive Summary

Extracted **6 atomic skills** from our experience with `actions/labeler@v5` across PRs #226 and #229. These skills prevent critical bugs in GitHub Actions label automation.

### Key Learnings

1. **Negation patterns require specific matcher types** - Cannot mix with inclusion patterns
2. **`all:` blocks enable complex AND logic** - Combine multiple matchers for inclusion + exclusion
3. **Four matcher types serve distinct purposes** - Choose based on ALL/ANY requirements

### Impact Metrics

| Metric | Value |
|--------|-------|
| Skills Extracted | 6 |
| Average Atomicity | 90% |
| High Impact (9-10) | 3 skills |
| Validated | 3 skills |
| Anti-Patterns Prevented | 6 |

---

## Skill Catalog

### Skill-Labeler-001: Negation Pattern Matcher Selection

**Statement**: Use `all-globs-to-all-files` matcher type for negation patterns in actions/labeler

**When to Apply**: When excluding paths with `!` prefix in actions/labeler configuration

**Evidence**:
- PR #226: Used `all-globs-to-all-files` with mixed patterns - [FAIL]
- PR #229 (c4799c9): Changed to `any-glob-to-any-file` - [FAIL]
- PR #229 (dae9db1): Isolated in `all-globs-to-all-files` within `all:` - [PASS]

**Atomicity**: 85/100

**Impact**: 9/10 - Prevents label misapplication on excluded paths

**Anti-Pattern**: Using `any-glob-to-any-file` with negation patterns (negations silently ignored)

---

### Skill-Labeler-002: Combined Matcher Block Pattern

**Statement**: Combine inclusion and exclusion patterns using `all:` block with separate matchers

**When to Apply**: When applying label based on file matches but excluding specific paths

**Evidence**: PR #229 (dae9db1) - Working config structure:

```yaml
documentation:
  - all:
      - changed-files:
          - any-glob-to-any-file:
              - "**/*.md"
      - changed-files:
          - all-globs-to-all-files:
              - "!.agents/**/*.md"
              - "!.serena/memories/**/*.md"
```

**Atomicity**: 90/100

**Impact**: 10/10 - Critical for correct exclusion logic

**Anti-Pattern**: Mixing inclusion and exclusion in single matcher block

---

### Skill-Labeler-003: Matcher Type Selection - ANY

**Statement**: Use `any-glob-to-any-file` when label applies if ANY file matches pattern

**When to Apply**: When labeling based on at least one file matching (most common use case)

**Evidence**:
- Current working config uses this for all simple area labels
- actions/labeler docs: "ANY glob must match against ANY changed file"
- Most permissive matching strategy

**Atomicity**: 95/100

**Impact**: 8/10 - Most common use case

**Anti-Pattern**: Using `all-globs-to-all-files` for simple file presence checks

**Example**:

```yaml
area-workflows:
  - changed-files:
      - any-glob-to-any-file:
          - ".github/workflows/**/*"
          - ".github/actions/**/*"
```

---

### Skill-Labeler-004: Matcher Type Selection - ALL FILES

**Statement**: Use `any-glob-to-all-files` when ALL changed files must match at least one pattern

**When to Apply**: When label should only apply if every changed file meets criteria

**Evidence**:
- actions/labeler docs: "ANY glob must match against ALL changed files"
- Use case: Ensure all files in PR meet quality criteria

**Atomicity**: 90/100

**Impact**: 7/10 - Less common but important for strict requirements

**Anti-Pattern**: Using `any-glob-to-any-file` when ALL files must match

**Example Use Case**: Apply "tests-only" label when all changed files are test files

```yaml
tests-only:
  - changed-files:
      - any-glob-to-all-files:
          - "**/*.test.ts"
          - "**/*.spec.ts"
```

---

### Skill-Labeler-005: Matcher Type Selection - ALL PATTERNS

**Statement**: Use `all-globs-to-any-file` when ALL patterns must find matches somewhere in changeset

**When to Apply**: When label requires multiple pattern types to be present

**Evidence**:
- actions/labeler docs: "ALL globs must match against ANY changed file"
- Example: Label when both `.ts` AND `.test.ts` files changed

**Atomicity**: 88/100

**Impact**: 6/10 - Specialized use case

**Anti-Pattern**: Using multiple separate matchers expecting AND logic (they OR by default)

**Example Use Case**: Apply "needs-tests" label only when both source and test files present

```yaml
has-tests:
  - changed-files:
      - all-globs-to-any-file:
          - "src/**/*.ts"
          - "**/*.test.ts"
```

---

### Skill-Labeler-006: Negation Pattern Isolation

**Statement**: Separate negation patterns into dedicated `all-globs-to-all-files` matcher within `all:` block

**When to Apply**: When excluding specific paths from broader pattern match

**Evidence**: Working pattern from PR #229 (dae9db1)

**Atomicity**: 92/100

**Impact**: 9/10 - Prevents subtle label misapplication bugs

**Anti-Pattern**: Mixing negation and inclusion in same matcher block

**Example**:

```yaml
documentation:
  # Correct: Separate inclusion and exclusion
  - all:
      - changed-files:
          - any-glob-to-any-file:
              - "**/*.md"
      - changed-files:
          - all-globs-to-all-files:
              - "!.agents/**/*.md"
              - "!.serena/memories/**/*.md"

  # WRONG: Mixed patterns (exclusions ignored)
  # - changed-files:
  #     - any-glob-to-any-file:
  #         - "**/*.md"
  #         - "!.agents/**/*.md"  # This will be ignored!
```

---

## Matcher Type Decision Matrix

| Requirement | Matcher Type | Use Case |
|-------------|--------------|----------|
| At least one file matches at least one pattern | `any-glob-to-any-file` | Most area labels |
| All files match at least one pattern | `any-glob-to-all-files` | Quality gates |
| All patterns find matches somewhere | `all-globs-to-any-file` | Multi-file-type requirements |
| All patterns match all files | `all-globs-to-all-files` | Negation patterns |

---

## Common Pitfalls

### Pitfall 1: Negation Patterns in Wrong Matcher

**Symptom**: Exclusion patterns silently ignored, labels applied to excluded paths

**Root Cause**: Using `any-glob-to-any-file` with `!` patterns

**Fix**: Use `all-globs-to-all-files` within `all:` block (see Skill-Labeler-001, Skill-Labeler-002)

### Pitfall 2: Expecting AND Logic by Default

**Symptom**: Label applied when only one condition met, expected both

**Root Cause**: Multiple top-level matchers use OR logic by default

**Fix**: Wrap in `all:` block or use `all-globs-to-any-file` (see Skill-Labeler-005)

### Pitfall 3: Wrong Matcher for Universal Requirements

**Symptom**: Label applied when only one file matches, expected all files to match

**Root Cause**: Using `any-glob-to-any-file` instead of `any-glob-to-all-files`

**Fix**: Use correct matcher type (see Skill-Labeler-004)

---

## Validation History

| Date | Skill | Test | Result | Evidence |
|------|-------|------|--------|----------|
| 2025-12-21 | Labeler-001 | Negation patterns in documentation label | [PASS] | PR #229 - excluded paths not labeled |
| 2025-12-21 | Labeler-002 | `all:` block pattern | [PASS] | PR #229 - combined matchers work |
| 2025-12-21 | Labeler-003 | Simple area labels | [PASS] | All area-* labels apply correctly |
| 2025-12-21 | Labeler-006 | Negation isolation | [PASS] | No false positives on excluded paths |

---

## Failure Analysis Reference

### PR #226: Initial Implementation

**Failures**:
1. Regex anchors only match combined content start (not individual title/body)
2. Negation patterns with `all-globs-to-all-files` mixed with inclusion patterns
3. Actions not pinned to commit SHAs

**Outcome**: Merged prematurely, required hotfix

### PR #229: Hotfix Evolution

**Attempt 1** (c4799c9):
- Changed to `any-glob-to-any-file` with negation patterns
- **Result**: [FAIL] - Negations still ignored

**Attempt 2** (dae9db1):
- Used `all:` block with separate matchers
- Inclusion: `any-glob-to-any-file`
- Exclusion: `all-globs-to-all-files`
- **Result**: [PASS] - Correct behavior

---

## Integration with Other Skills

### Complementary Skills

- **skill-git-001-pre-commit-validation**: Validate labeler.yml syntax before commit
- **skills-github-workflow-patterns**: Pin actions to commit SHAs
- **skill-protocol-002-verification-based-gate-effectiveness**: Require QA validation before merge

### Supersedes

None - these are novel skills for actions/labeler specifically

---

## References

- [actions/labeler Documentation](https://github.com/actions/labeler)
- PR #226: feat(workflows): add static PR and issue labeling workflows
- PR #229: fix(labeler): use all: block for negation patterns
- `.agents/retrospective/2025-12-22-pr-226-premature-merge-failure.md`
- `.github/labeler.yml` (current working configuration)

---

## Memory Location

**Serena Memory**: `.serena/memories/skills-github-actions-labeler.md`

**Retrieval Query**: `skill labeler negation matcher github actions`

---

## Maintenance Notes

### When to Update These Skills

- [ ] New matcher types added to actions/labeler
- [ ] Negation pattern behavior changes
- [ ] `all:` block syntax evolves
- [ ] Additional validation failures discovered

### Retirement Criteria

- [ ] actions/labeler changes architecture (unlikely)
- [ ] Better pattern matching solution available

---

**Last Updated**: 2025-12-21
**Next Review**: 2026-01-21 (or when actions/labeler v6 releases)
