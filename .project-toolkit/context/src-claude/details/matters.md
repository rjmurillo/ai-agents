## Matters

- Generated (ADR-109 B1 to B4): `agents/` 30, `rules/` 23 (repo-only rules stay in `.claude/rules/`), `skills/<name>/SKILL.md` 111, `hooks/` plus `hooks.json`.
- Hand-maintained: `claude-instructions.template.md`, `security/references/`, `.claude-plugin/plugin.json`, this file, `skills/<name>/` files but `SKILL.md`.
- Edit the template, never the render. A hand-edit fails its Template Drift gate next run.
- Agent frontmatter: `name`, `description`, `argument-hint` in all 30. `metadata.role` in 24. `tools:` only `analyst.md`, `security.md`.
- `skills/<name>/`: `SKILL.md` renders from its template; `scripts/`, `references/`, `tests/` are hand-maintained here.
