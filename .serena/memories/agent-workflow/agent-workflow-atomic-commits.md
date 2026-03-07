# Atomic Commit Strategy

**Statement**: Create atomic commits per logical unit for complex changes

**Context**: Multi-file changes requiring version control

**Evidence**: Enables selective rollback without reverting unrelated changes

**Atomicity**: 90%

**Impact**: 8/10

## Sequence

1. Config commit first
2. Each directory batch separately
3. Verify each batch before proceeding

## Pattern

```bash
# Config changes first
git add .markdownlint-cli2.yaml
git commit -m "chore: add markdownlint config"

# Then each batch
git add src/claude/**/*.md
git commit -m "fix: lint claude agent docs"

git add src/vs-code/**/*.md
git commit -m "fix: lint vs-code agent docs"
```

## Anti-Pattern

Monolithic commits containing all changes across multiple directories.

**Prevention**: Commit atomically by logical unit.

## Related

- [agent-workflow-004-proactive-template-sync-verification](agent-workflow-004-proactive-template-sync-verification.md)
- [agent-workflow-005-structured-handoff-formats](agent-workflow-005-structured-handoff-formats.md)
- [agent-workflow-collaboration](agent-workflow-collaboration.md)
- [agent-workflow-critic-gate](agent-workflow-critic-gate.md)
- [agent-workflow-mvp-shipping](agent-workflow-mvp-shipping.md)
