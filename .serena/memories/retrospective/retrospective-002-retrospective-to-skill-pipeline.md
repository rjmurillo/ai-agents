# Skill: Retrospective-to-Skill Pipeline

## Statement

Convert retrospective learnings into atomic skills with statement, context, pattern, evidence, and metrics.

## Context

After extracting learnings from PR or session retrospective. When transitioning from analysis phase to knowledge persistence.

## Pattern

### Workflow

1. **Input**: Analysis artifact with extracted learnings (e.g., `.agents/analysis/pr-255-learnings.md`)

2. **Skill transformation** (one per learning):
   - **Statement**: Imperative form (max 15 words) - what to do
   - **Context**: When to apply this skill
   - **Pattern**: Step-by-step guidance + good/bad examples
   - **Evidence**: Cite source (commit SHA, session number, PR number)
   - **Atomicity**: Score 0-100% (target 90%+)
   - **Category**: skill-creator, token-optimization, skill-structure, etc.
   - **Tag**: helpful | harmful | neutral
   - **Impact**: 1-10 rating
   - **Validation Count**: Starts at 1

3. **File naming**: `skill-{category}-{number}-{description}.md`
   - Example: `skill-creator-001-frontmatter-trigger-specification.md`

4. **Create index file**: `skill-{category}-best-practices-index.md`
   - Quick reference table
   - Links to individual skills
   - Total impact metrics

5. **Commit atomically**: Each skill or all skills + index in one commit

### Good Example

Session 65 pipeline:
- **Input**: `.agents/analysis/pr-255-learnings.md` (6 learnings)
- **Output**: 6 skill files + 1 index file
- **Naming**: `skill-creator-001` through `skill-creator-006`
- **Index**: `skill-creator-best-practices-index.md`
- **Commit**: Single commit with all 7 files

### Bad Example

- No index file (discoverability problem)
- Missing evidence section (no validation tracking)
- Vague statement (not actionable)
- No atomicity score (quality unknown)

## Evidence

**Session 65**: Generated 6 skills + index from PR #255 learnings
- Input: `.agents/analysis/pr-255-learnings.md`
- Output: 7 Serena memory files
- Commit: `56a2c37` - "Add skill-creator best practices (6 skills + index)"
- All skills scored 91-96% atomicity

## Atomicity

**Score**: 92%

**Justification**: Single concept (transform learnings into skills). Minor compound: includes both transformation process AND file management (naming, index), but these are core to the pipeline.

## Category

retrospective

## Tag

helpful

## Impact

**Rating**: 10/10

**Justification**: Core workflow for skill persistence. Ensures learnings become reusable, searchable skills. Enables cross-session knowledge continuity.

## Validation Count

1 (Session 65)

## Created

2025-12-22

## Activation Vocabulary

retrospective, skill, pipeline, learning, transformation, statement, context, pattern, evidence, atomicity, index, memory, Serena

## Related

- [retrospective-001-pr-learning-extraction](retrospective-001-pr-learning-extraction.md)
- [retrospective-001-recursive-extraction](retrospective-001-recursive-extraction.md)
- [retrospective-003-token-impact-documentation](retrospective-003-token-impact-documentation.md)
- [retrospective-004-evidence-based-validation](retrospective-004-evidence-based-validation.md)
- [retrospective-005-atomic-skill-decomposition](retrospective-005-atomic-skill-decomposition.md)
