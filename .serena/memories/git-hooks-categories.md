# Pre-Commit Hook Categories (ADR-004)

**Statement**: Pre-commit hooks fall into three categories with distinct behaviors

**Context**: Designing pre-commit validation hooks

**Evidence**: ADR-004 architecture decision

**Atomicity**: 95%

**Impact**: 9/10

## Categories

| Category | Behavior | Exit Code | Example |
|----------|----------|-----------|---------|
| BLOCKING | Fail commit on error | Non-zero | Syntax validation |
| WARNING | Warn but allow commit | Zero | Security detection |
| AUTO-FIX | Auto-fix then stage | Zero | Markdown lint, MCP sync |

## Design Principles

- Fail-fast for critical issues (invalid JSON, syntax errors)
- Warn-only for advisory (planning, security)
- Auto-fix when deterministic (markdown lint, config transforms)
- Security-hardened (symlink rejection, path validation)

## When to Use Pre-commit vs CI

| Pre-commit | CI |
|------------|-----|
| Fast (<2s) | Slow |
| Local-only | Network-dependent |
| Auto-fixable | Complex analysis |
| Non-destructive | Security-sensitive |
