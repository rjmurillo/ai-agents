# Skill Development Conventions

> **Scope**: Skills directory only. Auto-loaded when working in `.claude/skills/`.
> **Primary Reference**: Root CLAUDE.md and AGENTS.md take precedence.

## Skill Structure

```text
.claude/skills/{skill-name}/
├── SKILL.md              # Required: Frontmatter + prompt
├── modules/              # Optional: PowerShell modules
│   └── {Module}.psm1
├── scripts/              # Optional: PowerShell scripts
│   └── {Script}.ps1
├── templates/            # Optional: Templates, specs
│   └── {template}.md
└── tests/               # Optional: Pester tests
    └── {Module}.Tests.ps1
```

## Frontmatter Standards

### Required (Minimal)

```yaml
---
name: skill-identifier  # lowercase, alphanumeric + hyphens, max 64 chars
description: What the skill does and when to use it  # max 1024 chars
---
```

### Model Selection

Use **aliases** for automatic improvements:

```yaml
model: claude-haiku-4-5    # Speed, pattern matching (<1s, minimal cost)
model: claude-sonnet-4-5   # Standard workflows (<5s, standard cost)
model: claude-opus-4-5     # Orchestration, reasoning (<30s, premium justified)
```

## Validation Rules

- Frontmatter MUST start with `---` on line 1 (no blank lines)
- Use spaces for indentation (no tabs)
- Name format: `^[a-z0-9-]{1,64}$`
- Description: non-empty, max 1024 chars, include trigger keywords
- SKILL.md under 500 lines (use progressive disclosure)

## PowerShell Conventions

- Module imports: Use `-Force` for reloading during development
- Script structure: Param block, functions, main logic
- Error handling: `$ErrorActionPreference = 'Stop'` for failures
- Cross-platform: Test on Windows, Linux, macOS

## Testing

- Pester tests in `tests/` directory
- Test isolation: No global state modification
- Parameterized tests for multiple scenarios
- CI runs all tests on push

## Documentation

- SKILL.md is the primary documentation
- Include examples in frontmatter description
- Link to related skills/ADRs where applicable
- Keep skill-specific patterns in SKILL.md, not root docs

## Related References

- Skill frontmatter standards: `.serena/memories/claude-code-skill-frontmatter-standards.md`
- PowerShell standards: `scripts/CLAUDE.md`
- Official docs: https://code.claude.com/docs/en/skills
