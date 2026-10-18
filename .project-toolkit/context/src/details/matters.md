## Matters

- ADR-109 B1 to B5: `claude/{agents,skills,rules,hooks}` and `claude/hooks.json` render from `templates/`, `claude/lib/` from `scripts/`; binplace places them in `.claude/` (dogfood, no manifest or marketplace entry): `agents/`, `skills/`, `rules/` as symlinks here (ADR-119), the rest as copies. Render map: `templates/AGENTS.md`.
- `.claude-plugin/marketplace.json` lists one Claude plugin, `project-toolkit` at `./src/claude`; `claude-agents` is retired (B6).
- `claude/skills/<name>/`: `SKILL.md` renders from its template; every other file is hand-maintained here; `.claude/skills/<name>` links here (ADR-119).
