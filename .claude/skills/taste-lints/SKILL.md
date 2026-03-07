---
name: taste-lints
version: 1.0.0
model: claude-sonnet-4-5
description: Custom lints with agent-readable remediation instructions. Enforces taste invariants (file size, naming conventions, structured logging, complexity) and surfaces errors that agents can act on directly. Use when writing or reviewing code to catch style violations early.
license: MIT
---

# Taste Lints

Custom lints where error messages become agent-readable remediation instructions.

Inspired by [OpenAI Harness Engineering](https://openai.com/index/harness-engineering/):

> "We statically enforce structured logging, naming conventions for schemas and types,
> file size limits, and platform-specific reliability requirements with custom lints.
> Because the lints are custom, we write the error messages to inject remediation
> instructions into agent context."

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `run taste lints` | taste_lints.py on staged or specified files |
| `check file size` | taste_lints.py with file-size rule only |
| `check naming conventions` | taste_lints.py with naming rule only |
| `lint taste invariants` | taste_lints.py full scan |
| `taste lint report` | taste_lints.py with JSON output |

## When to Use

Use this skill when:

- Writing or editing source files (catch taste violations early)
- Preparing code for PR submission
- Reviewing code for style and convention compliance
- Adding new files to the project

## Taste Invariants

### 1. File Size Limits

Files exceeding line thresholds indicate poor cohesion.

| Threshold | Lines | Severity |
|-----------|-------|----------|
| Warning | 301-500 | warning |
| Error | 501+ | error |

### 2. Naming Conventions

| Pattern | Rule | Applies To |
|---------|------|------------|
| `snake_case` | Python files, functions, variables | `*.py` |
| `kebab-case` | Skill directories, YAML files | `.claude/skills/`, `*.yml` |
| `PascalCase` | PowerShell functions, classes | `*.ps1`, `*.psm1` |
| `UPPER_CASE` | Constants, environment variables | All languages |
| `invoke_` prefix | Hook scripts | `.claude/hooks/` |

### 3. Function Complexity

Functions exceeding cyclomatic complexity 10 need decomposition.

### 4. Skill Prompt Size

Skills exceeding 500 lines need progressive disclosure refactoring.

## Process

1. Run `python3 .claude/skills/taste-lints/scripts/taste_lints.py` with target files
2. Review AGENT_REMEDIATION blocks in output
3. Apply suggested fixes
4. Re-run to confirm compliance

## Usage

```bash
# Scan staged files
python3 .claude/skills/taste-lints/scripts/taste_lints.py --git-staged

# Scan specific files
python3 .claude/skills/taste-lints/scripts/taste_lints.py path/to/file.py

# Scan a directory
python3 .claude/skills/taste-lints/scripts/taste_lints.py --directory src/

# JSON output
python3 .claude/skills/taste-lints/scripts/taste_lints.py --format json --git-staged

# Run specific rules only
python3 .claude/skills/taste-lints/scripts/taste_lints.py --rules file-size,naming
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | No violations found |
| 1 | Script error (bad arguments, file not found) |
| 10 | Violations detected |
