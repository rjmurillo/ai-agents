# Git Hooks Domain Index

**Purpose**: Route to atomic skills for pre-commit hooks, auto-fix patterns, and cross-language integration.

**Source**: PR #52, ADR-004, Session protocol

## Activation Vocabulary

| Keywords | File |
|----------|------|
| pre-commit category blocking warning autofix exit-code fail-fast | git-hooks-categories |
| autofix auto-fix stage SKIP_AUTOFIX idempotent add | git-hooks-autofix |
| bash powershell cross-language integration pwsh exit return | git-hooks-cross-language |
| grep pattern anchor exact match substring false-positive | git-hooks-grep-patterns |
| TOCTOU security symlink race-condition check time-of-use | git-hooks-toctou |
| session validation checklist commit block protocol | git-hooks-session-validation |

## Domain Statistics

- **Skills**: 6 core patterns
- **Categories**: BLOCKING, WARNING, AUTO-FIX
- **Sources**: ADR-004, PR #52

## See Also

- `skills-bash-integration-index` - Bash exit code patterns
- `skills-security-index` - TOCTOU defense patterns
