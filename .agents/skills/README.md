# Skills Repository

This directory contains extracted learnings from agent execution, organized by category.

## Skill Categories

| File | Category | Skills | Anti-Patterns |
|------|----------|--------|---------------|
| `linting.md` | Code Quality and Documentation Standards | 9 | 2 |
| `documentation.md` | Documentation Generation and Maintenance | 10 | 2 |
| `multi-agent-workflow.md` | Agent Coordination and Workflow Patterns | 11 | 3 |

## Skill ID Convention

```text
Skill-[Category]-[Number]
Anti-[Category]-[Number]
```

Categories:

- **Lint**: Linting and code quality
- **Doc**: Documentation patterns
- **Workflow**: Multi-agent coordination

## Skill Structure

Each skill follows this format:

```markdown
## Skill-[Cat]-NNN: Short Title

- **Statement**: Atomic learning (max 15 words)
- **Context**: When this skill applies
- **Atomicity**: Score 0-100%
- **Evidence**: Specific execution details
- **Impact**: Measurable outcome
- **Tags**: helpful | harmful | neutral

[Additional details, patterns, examples]
```

## Atomicity Scoring

Skills are scored for atomicity:

| Score | Quality | Guidance |
|-------|---------|----------|
| 90-100% | Excellent | Ready for memory storage |
| 70-89% | Good | May need refinement |
| 50-69% | Acceptable | Consider splitting compound statements |
| <50% | Needs Work | Too vague or compound |

## Usage

### Citing Skills During Implementation

```markdown
**Applying**: Skill-Lint-001
**Strategy**: Run markdownlint --fix before manual edits
**Expected**: Auto-resolve spacing violations

[Execute...]

**Result**: 800+ violations auto-fixed
**Skill Validated**: Yes
```

### Adding New Skills

1. Identify the category (linting, documentation, workflow, etc.)
2. Create skill in appropriate file
3. Assign next available ID
4. Include all required fields
5. Calculate atomicity score
6. Add evidence from execution

### Tagging Skills

| Tag | Meaning | Criteria |
|-----|---------|----------|
| helpful | Contributed to success | Positive execution evidence |
| harmful | Caused failure | Negative execution evidence |
| neutral | No measurable impact | Used without effect |

## Source

Skills extracted from:

- 2025-12-13: Markdown Linting Implementation (Issue #14)

## Future Additions

As more features are implemented, add skills to:

- Existing category files if applicable
- New category files for new domains (e.g., `testing.md`, `security.md`)
