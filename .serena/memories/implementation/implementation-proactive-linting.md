# Skill-Implementation-003: Proactive Linting During File Creation

**Statement**: Run linters during file creation, not after implementation, to catch formatting issues early.

**Context**: File creation workflow in multi-file implementations.

**Trigger**: After creating or modifying markdown, YAML, or other lintable files.

**Evidence**: Session 03 (2025-12-18): 7 MD040 errors caught post-implementation; all could have been prevented with immediate linting after file creation.

**Atomicity**: 92%

**Impact**: 7/10 - Prevents cosmetic fix commits

## Pattern

```bash
# After creating markdown file
npx markdownlint-cli2 path/to/file.md --fix

# After creating YAML workflow
actionlint .github/workflows/new-workflow.yml
```

## Timing

| File Type | Lint Command | When |
|-----------|--------------|------|
| Markdown | `npx markdownlint-cli2 --fix` | After each `.md` Write |
| YAML workflow | `actionlint` | After each workflow Write |
| PowerShell | `Invoke-ScriptAnalyzer` | Before commit |

## Related

- [implementation-001-memory-first-pattern](implementation-001-memory-first-pattern.md)
- [implementation-001-pre-implementation-test-discovery](implementation-001-pre-implementation-test-discovery.md)
- [implementation-002-test-driven-implementation](implementation-002-test-driven-implementation.md)
- [implementation-006-graphql-first](implementation-006-graphql-first.md)
- [implementation-additive-approach](implementation-additive-approach.md)
