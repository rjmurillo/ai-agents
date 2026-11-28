## Matters

- ADR-109: `claude/{agents,skills,rules,hooks}` render from `templates/`. Dogfood `.claude/` links agents, skills, and rules (ADR-119). See `templates/AGENTS.md`.
- `.claude-plugin/marketplace.json` lists one Claude plugin, `project-toolkit` at `./src/claude`; `claude-agents` is retired (B6).
- `claude/skills/<name>/`: `SKILL.md` renders from its template; every other file is hand-maintained here; `.claude/skills/<name>` links here (ADR-119).
