---
applyTo: ".claude/skills/**/*"
---

# Claude Skills Standards

For comprehensive skill development guidance, see [.agents/steering/claude-skills.md](../../.agents/steering/claude-skills.md).

## Quick Reference

**Language:** Python 3.10+ for new scripts (ADR-042). PowerShell for existing script maintenance.

**Required files:** Every skill directory needs `SKILL.md` with frontmatter (name, description).

**Scope control:**

- One skill per PR
- 10 or fewer files per PR
- No memory, hook, or ADR changes in skill PRs (use separate PRs)

**Before PR:**

- SKILL.md frontmatter validates
- Tests pass (pytest or Pester)
- No unrelated file changes
