# Task Completion Checklist

When completing a task in this repository, follow this checklist:

## Before Committing

### 1. Markdown Linting

```bash
# Run linting to check for issues
npx markdownlint-cli2 "**/*.md"

# Or auto-fix issues
npx markdownlint-cli2 --fix "**/*.md"
```

### 2. Pre-commit Hook

If not already enabled:

```bash
uv run --frozen lefthook install
```

This will auto-fix markdown issues on commit.

Do not set `core.hooksPath` by hand. `.githooks` is not tracked in this
repository, so pointing `core.hooksPath` at it makes git run no hook and print
no warning, which silently disabled every pre-commit and pre-push job twice
(issue #5090, a repeat of the 2026-07-19 repair). To repair a clone that
already carries the setting, run `uv run --frozen lefthook install --reset-hooks-path`.

### 3. Common Markdown Issues to Check

- [ ] All code blocks have language identifiers
- [ ] Generic types wrapped in backticks (e.g., `List<T>`)
- [ ] Blank lines around headings, lists, and code blocks
- [ ] No inline HTML (except allowed elements: br, kbd, sup, sub)

## Commit Standards

### Commit Message Format

```text
<type>(<scope>): <description>

<optional body>
```

Types: feat, fix, docs, style, refactor, test, chore

### Atomic Commits

- Create atomic commits for each logical change
- Reference issues in commit messages: `fixes #123`

## Agent Output Locations

Save artifacts to appropriate directories in `.agents/`:

| Type | Directory |
|------|-----------|
| Analysis findings | `.agents/analysis/` |
| ADRs | `.agents/architecture/` |
| Plans and PRDs | `.agents/planning/` |
| Plan reviews | `.agents/critique/` |
| Test reports | `.agents/qa/` |
| Retrospectives | `.agents/retrospective/` |

## Post-Task

### Memory Updates

Store learnings using cloudmcp-manager:

```python
mcp__cloudmcp-manager__memory-add_observations(...)
mcp__cloudmcp-manager__memory-create_entities(...)
```

### Skill Citation

When applying learned strategies:

```markdown
**Applying**: Skill-Build-001
**Strategy**: [description]
**Expected**: [outcome]
**Result**: [actual outcome]
**Skill Validated**: Yes/No
```

## Testing

This repository is primarily documentation/configuration, so:

- No unit tests to run
- Linting serves as the primary quality gate
- Manual review of agent behavior recommended
