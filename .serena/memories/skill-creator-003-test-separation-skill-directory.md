# Skill-Creator-003: Test Separation from Skill Directory

## Statement

Pester tests MUST be located in `.github/tests/skills/{skill-name}/`, NOT in the skill directory. Tests validate skill quality (CI concern), not skill execution (runtime concern).

## Context

When organizing skill directories for Claude Code skills.

## Pattern

**Bad (tests in skill)**:

```text
.claude/skills/github/
├── SKILL.md
├── scripts/
└── tests/              ❌ Tests here consume ~1,500 tokens
    └── MyScript.Tests.ps1
```

**Good (tests separate)**:

```text
.claude/skills/github/
├── SKILL.md
├── scripts/
└── modules/

.github/tests/skills/github/   ✅ Tests here, not in context
└── MyScript.Tests.ps1
```

## Why This Matters

- Tests are for CI validation, not skill execution
- Claude doesn't need test code when using the skill
- Skill directory should contain ONLY execution-relevant files
- Token savings: ~1,500 tokens per skill

## Evidence

PR #255 (2025-12-22): Tests moved from `.claude/skills/github/tests/` to `.github/tests/skills/github/`. Commit `04e19e8`.

## Metrics

- Atomicity: 94%
- Category: skill-structure, token-optimization
- Created: 2025-12-22
- Tag: skill-creator
- Validated: 1 (PR #255)

## Related Skills

- Skill-Creator-002 (comment stripping)
- Skill-Creator-005 (schema redundancy)
