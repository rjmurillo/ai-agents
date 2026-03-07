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

### Required (Full, for SkillForge validation)

```yaml
---
name: skill-identifier
version: 1.0.0
model: claude-sonnet-4-5
description: What the skill does and when to use it
license: MIT
---
```

### Model Selection

Use **aliases** for automatic improvements:

```yaml
model: claude-haiku-4-5    # Speed, pattern matching (<1s, minimal cost)
model: claude-sonnet-4-5   # Standard workflows (<5s, standard cost)
model: claude-opus-4-5     # Orchestration, reasoning (<30s, premium justified)
```

## Modularity Guidelines (SkillsBench)

SkillsBench (Feb 2026) found that smaller, modular skills outperform large data dumps.
Human-curated skills boost task completion by +16.2%. Self-generated skills hurt by -1.3%.

| Guideline | Target | Why |
|-----------|--------|-----|
| SKILL.md lines | <=300 ideal, 500 max | Smaller skills outperform large dumps |
| Top-level sections (h2) | <=10 | Signals single responsibility |
| Progressive disclosure | Use scripts/, references/, templates/ | Keeps prompt focused, details accessible |
| Modularity score | >=80 | Run `python3 scripts/validation/skill_modularity_audit.py` |

When a skill exceeds these targets, refactor by:
1. Extract reference tables and examples to `references/`
2. Move procedural logic to `scripts/`
3. Split skills with >10 h2 sections into focused sub-skills
4. Use `templates/` for structured output formats

Audit command: `python3 scripts/validation/skill_modularity_audit.py [--json] [--ci]`

## Validation Rules

- Frontmatter MUST start with `---` on line 1 (no blank lines)
- Use spaces for indentation (no tabs)
- Name format: `^[a-z0-9-]{1,64}$`
- Description: non-empty, max 1024 chars, include trigger keywords
- SKILL.md under 500 lines (use progressive disclosure)

### Prompt Size Limits

| Threshold | Lines | Behavior |
|-----------|-------|----------|
| Normal | 0-300 | No action |
| Warning | 301-500 | Warning in pre-commit output |
| Error | 501+ | Blocks commit (CI mode) |

When a skill exceeds 500 lines, refactor using progressive disclosure:

- Move reference documentation to `references/`
- Extract reusable logic to `modules/` or `scripts/`
- Use templates in `templates/` for structured output

To declare a justified exception, add `size-exception: true` to frontmatter:

```yaml
---
name: complex-skill
size-exception: true
description: Justified overage due to embedded decision trees
---
```

Validated by: `scripts/validation/skill_size.py`

## SkillForge Validator Gotchas

- `version` and `model` MUST be top-level YAML keys, not nested under `metadata:`
- Trigger phrases must be backtick-wrapped (`` `phrase` ``), not quote-wrapped
- Validator requires 3-5 trigger phrases per skill
- Process section: matches `## Process` (h2) or `### Phase N` (h3), not `## Phase N`
- Parallel agents staging files can lock git index; use `git diff --staged` to check

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
- PowerShell standards: `scripts/AGENTS.md`
- Official docs: <https://code.claude.com/docs/en/skills>
