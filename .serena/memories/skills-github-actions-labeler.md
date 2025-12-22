# GitHub Actions Labeler Skills

**Source**: PR #226, PR #229 (hotfix), Retrospective 2025-12-22
**Category**: Tool-Labeler
**Domain**: GitHub Actions, Workflow Automation
**Evidence Quality**: High (multiple PR failures → working solution)

---

## Skill-Labeler-001: Negation Pattern Matcher Selection

**Statement**: Use `all-globs-to-all-files` matcher type for negation patterns in actions/labeler

**Context**: When excluding paths with `!` prefix in actions/labeler configuration

**Evidence**:
- PR #226: Used `all-globs-to-all-files` with negation patterns mixed with inclusion - FAILED
- PR #229 (c4799c9): Changed to `any-glob-to-any-file` with negation patterns - FAILED
- PR #229 (dae9db1): Isolated negations in `all-globs-to-all-files` within `all:` block - PASS

**Atomicity**: 85%
- Length: 11 words ✓
- Single concept: Negation matcher type
- Actionable: Yes
- Evidence-based: Yes

**Tag**: helpful
**Impact**: 9/10 (prevents label misapplication on excluded paths)
**Created**: 2025-12-21
**Validated**: 1 (PR #229 success)

**Anti-Pattern**: Using `any-glob-to-any-file` with negation patterns (negations ignored)

---

## Skill-Labeler-002: Combined Matcher Block Pattern

**Statement**: Combine inclusion and exclusion patterns using `all:` block with separate matchers

**Context**: When applying label based on file matches but excluding specific paths

**Evidence**:
- PR #229 (dae9db1): Working config structure:
  ```yaml
  documentation:
    - all:
        - changed-files:
            - any-glob-to-any-file:
                - "**/*.md"
        - changed-files:
            - all-globs-to-all-files:
                - "!.agents/**/*.md"
  ```

**Atomicity**: 90%
- Length: 11 words ✓
- Single concept: Pattern combination strategy
- Actionable: Yes
- Evidence-based: Yes

**Tag**: helpful
**Impact**: 10/10 (critical for correct exclusion logic)
**Created**: 2025-12-21
**Validated**: 1 (PR #229 success)

**Anti-Pattern**: Mixing inclusion and exclusion in single matcher block

---

## Skill-Labeler-003: Matcher Type Selection - ANY

**Statement**: Use `any-glob-to-any-file` when label applies if ANY file matches pattern

**Context**: When labeling based on at least one file matching (most common use case)

**Evidence**:
- Current working config uses this for all simple area labels (area-workflows, area-prompts, etc.)
- actions/labeler docs: "ANY glob must match against ANY changed file"
- Most permissive matching strategy

**Atomicity**: 95%
- Length: 12 words ✓
- Single concept: Matcher selection for ANY logic
- Actionable: Yes
- Clear criteria: Yes

**Tag**: helpful
**Impact**: 8/10 (most common use case)
**Created**: 2025-12-21
**Validated**: 1 (all simple labels work correctly)

**Anti-Pattern**: Using `all-globs-to-all-files` for simple file presence checks

---

## Skill-Labeler-004: Matcher Type Selection - ALL FILES

**Statement**: Use `any-glob-to-all-files` when ALL changed files must match at least one pattern

**Context**: When label should only apply if every changed file meets criteria

**Evidence**:
- actions/labeler docs: "ANY glob must match against ALL changed files"
- Use case: Ensure all files in PR meet quality criteria (e.g., all files are tests)

**Atomicity**: 90%
- Length: 14 words ✓
- Single concept: Universal file requirement
- Actionable: Yes

**Tag**: helpful
**Impact**: 7/10 (less common but important for strict requirements)
**Created**: 2025-12-21
**Validated**: 0 (not yet used in our config but documented)

**Anti-Pattern**: Using `any-glob-to-any-file` when ALL files must match

---

## Skill-Labeler-005: Matcher Type Selection - ALL PATTERNS

**Statement**: Use `all-globs-to-any-file` when ALL patterns must find matches somewhere in changeset

**Context**: When label requires multiple pattern types to be present

**Evidence**:
- actions/labeler docs: "ALL globs must match against ANY changed file"
- Example: Label when both `.ts` AND `.test.ts` files changed

**Atomicity**: 88%
- Length: 13 words ✓
- Single concept: Multi-pattern requirement
- Actionable: Yes

**Tag**: helpful
**Impact**: 6/10 (specialized use case)
**Created**: 2025-12-21
**Validated**: 0 (not yet used but documented)

**Anti-Pattern**: Using multiple separate matchers expecting AND logic (they OR by default)

---

## Skill-Labeler-006: Negation Pattern Isolation

**Statement**: Separate negation patterns into dedicated `all-globs-to-all-files` matcher within `all:` block

**Context**: When excluding specific paths from broader pattern match

**Evidence**:
- Working pattern from PR #229 (dae9db1):
  - Positive patterns: `any-glob-to-any-file: ["**/*.md"]`
  - Negative patterns: `all-globs-to-all-files: ["!.agents/**/*.md", "!.serena/**/*.md"]`
  - Combined with `all:` block for AND logic

**Atomicity**: 92%
- Length: 12 words ✓
- Single concept: Negation isolation
- Actionable: Yes
- Evidence-based: Yes

**Tag**: helpful
**Impact**: 9/10 (prevents subtle label misapplication bugs)
**Created**: 2025-12-21
**Validated**: 1 (PR #229 success)

**Anti-Pattern**: Mixing negation and inclusion in same matcher block

---

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total Skills | 6 |
| Average Atomicity | 90% |
| Validated Skills | 3 |
| Impact 9-10 | 3 |
| Impact 6-8 | 3 |
| Evidence Quality | High (failed PRs → working solution) |

## Related Documents

- `.github/labeler.yml` - Current working configuration
- `.agents/retrospective/2025-12-22-pr-226-premature-merge-failure.md` - Failure analysis
- PR #226 - Initial implementation with defects
- PR #229 - Hotfix with correct negation pattern handling

## Validation History

| Date | Skill | Result | Evidence |
|------|-------|--------|----------|
| 2025-12-21 | Labeler-001 | [PASS] | PR #229 labels apply correctly with exclusions |
| 2025-12-21 | Labeler-002 | [PASS] | `all:` block pattern works as expected |
| 2025-12-21 | Labeler-003 | [PASS] | All simple area labels work |
| 2025-12-21 | Labeler-006 | [PASS] | Negation isolation prevents bug recurrence |
