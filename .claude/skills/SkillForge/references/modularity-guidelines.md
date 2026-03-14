# Modularity Guidelines (SkillsBench)

SkillsBench (Feb 2026) found that smaller, modular skills outperform large data dumps.
Human-curated skills boost task completion by +16.2%. Self-generated skills hurt by -1.3%.

| Guideline | Target | Why |
|-----------|--------|-----|
| SKILL.md lines | <=300 ideal, 500 max | Smaller skills outperform large dumps |
| Top-level sections (h2) | <=10 | Signals single responsibility |
| Progressive disclosure | Use scripts/, references/, templates/ | Keeps prompt focused, details accessible |
| Modularity score | >=80 | Run modularity audit script |

## Refactoring Targets

When a skill exceeds these targets, refactor by:

1. Extract reference tables and examples to `references/`
2. Move procedural logic to `scripts/`
3. Split skills with >10 h2 sections into focused sub-skills
4. Use `templates/` for structured output formats

## Audit Command

```bash
python3 .claude/skills/SkillForge/scripts/skill_modularity_audit.py [--json] [--ci]
```
