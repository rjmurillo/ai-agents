# Skill: Evidence-Based Skill Validation

## Statement

Link each skill to specific commits or PRs as evidence, enabling validation count tracking.

## Context

When generating skills from observed patterns, whether from PRs, sessions, or retrospectives.

## Pattern

### Workflow

1. **Include evidence section in every skill**:
   - Cite specific commit SHA(s)
   - Reference PR number
   - Link to session log or analysis artifact
   - Describe what was observed

2. **Track validation count**:
   - Starts at 1 (initial observation)
   - Increment when pattern is reused successfully
   - Decrement or tag as "harmful" if pattern fails

3. **Evidence format**:
   ```markdown
   ## Evidence

   **Session [N]**: [Description]
   - Commit: [SHA] - "[commit message]"
   - PR: #[number]
   - Outcome: [quantified result]
   ```

4. **Update validation on reuse**:
   - When skill is applied in new context, add observation to evidence section
   - Increment validation count
   - Document new commit/PR/session

### Good Example

From Session 65 skill-creator-002:
```markdown
## Evidence

**Session 65**: Token savings from PR #255
- Commit: `69fffd6` - "Token savings: ~2,400 tokens when Claude loads the config"
- Before: 273 lines (copilot-synthesis.yml with comments)
- After: 27 lines (config only)
- Impact: ~2,400 tokens saved

## Validation Count

1 (Session 65)
```

### Bad Example

```markdown
## Evidence

This pattern works well.

## Validation Count

1
```

**Problems**: No commit SHA, no PR reference, no quantified outcome, no way to verify claim.

## Evidence

**Session 65**: All 6 skills cite specific commits
- skill-creator-001: Cites commit with frontmatter change
- skill-creator-002: Cites commit `69fffd6` (comment stripping)
- skill-creator-003: Cites commit `04e19e8` (test separation)
- skill-creator-004: Cites commit `c0a3c1f` (reference extraction)
- skill-creator-005: Cites commit `ae58331` (schema deletion)
- skill-creator-006: Cites commit `e8635fc` (TOC addition)

**Validation count**: All skills start at 1, ready for increment on reuse.

## Atomicity

**Score**: 93%

**Justification**: Single concept (link skills to evidence). Minor compound: evidence + validation tracking, but validation count is meaningless without evidence.

## Category

retrospective

## Tag

helpful

## Impact

**Rating**: 9/10

**Justification**: Prevents skill drift (pattern described accurately). Enables validation tracking (which skills are reused?). Provides audit trail for skill quality.

## Validation Count

1 (Session 65)

## Created

2025-12-22

## Activation Vocabulary

evidence, validation, commit, SHA, PR, tracking, count, observation, reuse, audit, verification, source

## Related

- [retrospective-001-pr-learning-extraction](retrospective-001-pr-learning-extraction.md)
- [retrospective-001-recursive-extraction](retrospective-001-recursive-extraction.md)
- [retrospective-002-retrospective-to-skill-pipeline](retrospective-002-retrospective-to-skill-pipeline.md)
- [retrospective-003-token-impact-documentation](retrospective-003-token-impact-documentation.md)
- [retrospective-005-atomic-skill-decomposition](retrospective-005-atomic-skill-decomposition.md)
