# Retrospective Skill Persistence Protocol

**Type**: MANDATORY
**Category**: Agent Workflow
**Source**: 2025-12-24 User Directive

## Requirement

After EVERY retrospective, you MUST persist extracted skills to Serena memory.

## Process

1. **During retrospective**: Extract skills with SMART validation and atomicity scores
2. **After retrospective complete**: 
   - Create individual memory files for each skill (`skill-{domain}-{number}`)
   - Update relevant index files (`skills-{domain}-index`)
   - Create anti-pattern memories for harmful patterns
3. **Verification**: Confirm all skills persisted before claiming completion

## Skill File Format

Use descriptive kebab-case names without `skill-` prefix:
- [pr-enum-001](pr-enum-001.md) not `skill-pr-enum-001`
- [git-worktree-parallel](git-worktree-parallel.md) not `skill-git-worktree-001`

```markdown
# {Title}

**Atomicity**: {score}%
**Category**: {category}
**Source**: {date} {session name}

## Statement
{one-sentence skill statement}

## Context
{when to apply}

## Evidence
{specific evidence from session}

## Pattern
{code or process pattern}
```

## Index Update Format

Add row to `skills-{domain}-index`:
```
| {keywords} | {skill-file-name} |
```

## Anti-Pattern Format

Prefix with `[HARMFUL]` in index:
```
| [HARMFUL] {keywords} | anti-pattern-{domain}-{number} |
```

## Failure Mode

If skills are NOT persisted after retrospective:
- Learnings are lost across sessions
- Same mistakes repeat
- Knowledge does not accumulate

This is a BLOCKING requirement. Do not claim retrospective complete without skill persistence.

## Related

- [retrospective-001-pr-learning-extraction](retrospective-001-pr-learning-extraction.md)
- [retrospective-001-recursive-extraction](retrospective-001-recursive-extraction.md)
- [retrospective-002-retrospective-to-skill-pipeline](retrospective-002-retrospective-to-skill-pipeline.md)
- [retrospective-003-token-impact-documentation](retrospective-003-token-impact-documentation.md)
- [retrospective-004-evidence-based-validation](retrospective-004-evidence-based-validation.md)
