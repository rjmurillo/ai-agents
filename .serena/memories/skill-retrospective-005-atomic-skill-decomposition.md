# Skill: Atomic Skill Decomposition

## Statement

Break multi-faceted improvements into individual skills, one per distinct concept.

## Context

When a PR contains multiple improvements, each representing a different pattern or concern.

## Pattern

### Workflow

1. **Identify distinct concepts**:
   - Read PR commits and changes
   - Look for: different problem statements, different solutions, different categories
   - Ask: "Could this pattern be reused independently?"

2. **One skill per pattern**:
   - NOT one skill per PR
   - NOT one skill per commit (commits may bundle multiple patterns)
   - YES one skill per atomic, reusable concept

3. **Score atomicity**:
   - 95-100%: Excellent (single concept, no compound statements)
   - 90-94%: Good (minor compound, but inseparable)
   - 85-89%: Acceptable (some bundling, consider splitting)
   - <85%: Needs decomposition

4. **Ensure independent reusability**:
   - Each skill should be actionable on its own
   - Skill A should not require reading Skill B to understand
   - Avoid "also" or "and" in statement (indicates bundling)

5. **Avoid combining unrelated patterns**:
   - Token optimization ≠ test organization
   - Frontmatter format ≠ file naming
   - Documentation structure ≠ schema validation

### Good Example

Session 65 (PR #255):
- **PR**: 8 commits, multiple improvements
- **Skills**: 6 atomic skills (NOT 1 skill called "improve GitHub skill")
  - skill-creator-001: Frontmatter triggers (95% atomicity)
  - skill-creator-002: Comment stripping (92% atomicity)
  - skill-creator-003: Test separation (94% atomicity)
  - skill-creator-004: Reference extraction (91% atomicity)
  - skill-creator-005: Schema deletion (96% atomicity)
  - skill-creator-006: TOC requirement (93% atomicity)
- **Range**: 91-96% atomicity (all high quality)

### Bad Example

Single skill: "Optimize GitHub skill by stripping comments, moving tests, deleting schemas, and adding TOCs"
- **Atomicity**: ~40% (4 unrelated concepts)
- **Reusability**: Poor (which part do I apply?)
- **Evidence**: Unclear (which commits support which patterns?)

## Evidence

**Session 65**: Split PR #255 into 6 atomic skills
- Input: 1 PR with 8 commits
- Output: 6 skills (1 per distinct pattern)
- Atomicity range: 91-96% (all high quality)
- Each skill independently reusable

**Comparison**: Could have created 1 skill ("PR #255 patterns") or 8 skills (one per commit). Instead, identified 6 distinct concepts based on reusability principle.

## Atomicity

**Score**: 96%

**Justification**: Single concept (one skill per pattern). No compound statements. Highly actionable.

## Category

retrospective

## Tag

helpful

## Impact

**Rating**: 10/10

**Justification**: Core principle for skill quality. Prevents bloated, multi-purpose skills. Maximizes reusability. Enables precise application.

## Validation Count

1 (Session 65)

## Created

2025-12-22

## Activation Vocabulary

atomic, decomposition, skill, pattern, reusability, concept, distinct, independent, one, single, split, granular, separation
