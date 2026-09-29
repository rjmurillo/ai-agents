## Matters

- Generated (ADR-109 B1 to B4): `agents/` 30, `rules/` 28, `skills/<name>/SKILL.md` 111, `hooks/` plus `hooks.json`.
- Hand-maintained: `claude-instructions.template.md`, `security/references/`, `.claude-plugin/plugin.json`, this file.
- Edit the template, never the render. A hand-edit fails its Template Drift gate next run.
- Agent frontmatter: `name`, `description`, `argument-hint` in all 30. `metadata.role` in 24. `tools:` only `analyst.md`, `security.md`. `model:` only `code-reviewer.md`.
- `skills/<name>/`: `SKILL.md` renders from its template; `scripts/`, `references/`, `tests/` are build mirrors of `.claude/skills/<name>/`, the hand-maintained source. Edit there.
