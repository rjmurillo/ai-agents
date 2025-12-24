# Skill-Lint-001: Autofix Before Manual Edits

**Statement**: Run `markdownlint --fix` before manual edits to auto-resolve spacing violations

**Context**: Large-scale markdown linting with 100+ files

**Evidence**: 2025-12-13 - auto-fixed 800+ MD031/MD032/MD022 spacing errors instantly

**Atomicity**: 95%

**Impact**: Reduced manual edit effort by 60%

## Application

```bash
npx markdownlint-cli2 --fix "**/*.md"
```

## Batch Fixes by Directory

Fix lint violations in directory batches with atomic commits per batch:

1. Fix claude/ → verify → commit
2. Fix vs-code-agents/ → verify → commit
3. Fix copilot-cli/ → verify → commit

## Anti-Pattern

- Manual editing every file individually for mechanical fixes
- **Prevention**: Always run `--fix` first
