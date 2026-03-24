---
applyTo: ".claude/skills/**"
---

# Claude Skills Standards

For comprehensive skill development standards, see [.agents/steering/claude-skills.md](../../.agents/steering/claude-skills.md).

## Quick Reference - Skills

**Structure:**

```text
.claude/skills/<skill-name>/
├── SKILL.md              # Frontmatter + prompt (REQUIRED)
├── scripts/              # Implementation scripts
└── references/           # Optional supporting docs
```

**Key Principles:**

- One skill, one purpose
- SKILL.md frontmatter required (name, version, description)
- Python for new scripts (ADR-042)
- Tests required for all scripts
- File count per PR: 10 or fewer
- Memory changes in separate PR

*This file serves as a Copilot-specific entry point. The authoritative steering content is maintained in `.agents/steering/claude-skills.md`.*
