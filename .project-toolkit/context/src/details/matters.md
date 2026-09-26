## Matters

- ADR-109 B1 to B5: `claude/{agents,skills,rules,hooks}` and `claude/hooks.json` render from `templates/`, `claude/lib/` from `scripts/`; binplace copies each byte for byte into `.claude/`, the dogfood copy with no manifest and no marketplace entry. Render map: `templates/AGENTS.md`.
- `.claude-plugin/marketplace.json` lists one Claude plugin, `project-toolkit` at `./src/claude`; `claude-agents` is retired (B6).
- `claude/skills/<name>/`: `SKILL.md` renders from its template; every other file mirrors from `.claude/skills/<name>/`, the hand-maintained source (`sync_claude_plugin_skill_support`, `merge-resolver` included).
