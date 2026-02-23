---
name: Claude Skills
applyTo: ".claude/skills/**"
excludeFrom: ".claude/skills/**/*.Tests.ps1"
priority: 8
version: 1.0.0
status: active
---

# Claude Skills Steering

## Scope

**Applies to**:

- `.claude/skills/**` - All files in the Claude skills directory

**Excludes**:

- `.claude/skills/**/*.Tests.ps1` - Pester test files (see testing-approach.md)

## Pre-Flight Checks

Before creating or modifying a skill, verify:

1. **New or update?** Check `.claude/skills/` for an existing skill with overlapping purpose.
2. **Duplicate check**: Search skill SKILL.md files for similar `description` or `triggers`.
3. **Memory context**: Load the skill's Serena memory if it exists (e.g., `skills-<name>-index`).

## Guidelines

### Skill Structure

Every skill MUST have this directory layout:

```text
.claude/skills/<skill-name>/
├── SKILL.md              # Frontmatter + prompt (REQUIRED)
├── scripts/              # Implementation scripts
│   └── <script>.py       # Python for new scripts (ADR-042)
└── references/           # Optional supporting docs
```

### SKILL.md Frontmatter

Every SKILL.md MUST include valid YAML frontmatter:

```yaml
---
name: skill-name
version: 1.0.0
model: claude-sonnet-4-5
description: >-
  One-paragraph description of what the skill does.
  Starts with a verb. Under 200 characters.
license: MIT
---
```

Required fields: `name`, `version`, `description`.
Optional fields: `model`, `license`.

### Language Policy

| Scenario | Language | Authority |
|----------|----------|-----------|
| New scripts | Python (.py) | ADR-042 |
| Existing PowerShell scripts | PowerShell (.ps1/.psm1) | ADR-042 |
| Hooks (pre-commit, etc.) | Python (.py) | ADR-042 |
| Bash scripts | Prohibited | ADR-005, ADR-042 |

**Rationale**: ADR-042 establishes Python-first development. Existing PowerShell scripts are grandfathered.

### Testing Requirements

- Every script MUST have corresponding tests.
- Python scripts: pytest tests in `tests/` directory.
- PowerShell scripts: Pester tests co-located with scripts.
- Target: 80% code coverage minimum.
- See `testing-approach.md` steering for Pester conventions.

### Scope Control

A skill has one purpose. Signs of scope explosion:

| Signal | Threshold | Action |
|--------|-----------|--------|
| File count in PR | > 10 files | Split into separate PRs |
| Commit count | > 20 commits | Squash or split |
| Memory file changes | > 0 memory files | Move to separate PR |
| Multiple unrelated features | > 1 feature | One skill, one PR |

Memory changes (`.serena/memories/`) belong in a **separate PR** from skill implementation.

### Naming Conventions

| Item | Convention | Example |
|------|-----------|---------|
| Skill directory | kebab-case | `code-qualities-assessment` |
| SKILL.md `name` | kebab-case, matches directory | `code-qualities-assessment` |
| Python scripts | snake_case | `analyze_code.py` |
| PowerShell scripts | PascalCase with verb-noun | `Get-ApplicableSteering.ps1` |
| Serena memories | kebab-case with prefix | `skills-github-cli-index` |

## Patterns

### Minimal Skill (Python)

```text
.claude/skills/my-skill/
├── SKILL.md
└── scripts/
    └── my_skill.py
```

SKILL.md delegates to the script:

```markdown
When this skill activates, IMMEDIATELY invoke the script. The script IS the workflow.
```

### Skill with References

```text
.claude/skills/prompt-engineer/
├── SKILL.md
├── scripts/
│   └── optimize_prompt.py
└── references/
    └── prompt-engineering-patterns.md
```

Reference files provide domain knowledge. They do not contain executable logic.

## Before PR Checklist

Before submitting a skill PR, verify:

- [ ] SKILL.md has valid frontmatter (name, version, description)
- [ ] No duplicate skill exists with overlapping purpose
- [ ] Scripts use Python for new code (ADR-042)
- [ ] Tests exist and pass
- [ ] File count in PR is 10 or fewer
- [ ] Commit count is 20 or fewer
- [ ] No memory file changes included (separate PR)
- [ ] Skill directory uses kebab-case naming

## Anti-Patterns

### Scope Explosion

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| Skill + hook + memory in one PR | Unbounded scope, hard to review | Separate PRs per concern |
| Renaming memory conventions mid-PR | Creates cascading changes | Plan naming upfront, use separate PR |
| Adding "bonus" features | Delays review, introduces risk | One skill, one purpose |

### Missing Validation

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| No SKILL.md frontmatter | Tooling cannot discover the skill | Add required YAML fields |
| No tests | Regressions go undetected | Write tests before or with implementation |
| Hardcoded paths | Breaks in different environments | Use relative paths from `$PSScriptRoot` or `__file__` |

### Language Violations

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| New bash scripts in skills | Violates ADR-005 and ADR-042 | Use Python |
| New PowerShell for greenfield work | Misses ADR-042 guidance | Use Python for new scripts |

## References

- [ADR-005](../../.agents/architecture/ADR-005-powershell-only-scripting.md): Original PowerShell-only decision (superseded for new development)
- [ADR-042](../../.agents/architecture/ADR-042-python-migration-strategy.md): Python migration strategy (current)
- [SKILL-AUTHORING.md](../../docs/SKILL-AUTHORING.md): Skill authoring guide
- [Steering README](.agents/steering/README.md): Steering system overview
- Memory: `skills-index`

---

*Created: 2026-02-22*
*GitHub Issue: #951*
