## Matters

- Generated, never hand-edit: `agents/`, `rules/`, `skills/<name>/SKILL.md`, `hooks/`, `settings.json`, `lib/` packages plus `lib/bootstrap.py`. Sources: `templates/` and the `scripts/` packages of `rjmurillo/ai-agents`.
- Hand-maintained here: `lib/` (mixed, see next line), `CLAUDE.md`, this guide, the seven doc files under `hooks/`, repo-local skills' non-`SKILL.md` files. No manifest: `.claude-plugin/plugin.json` was deleted at B6.
- `lib/` mixed: shipped entries link into `src/claude/lib/` (ADR-119). Edit the source: packages and `bootstrap.py` in `scripts/<pkg>/`; `paths.py`, `ptk_run.py` in `src/claude/lib/`. Other modules here are real files.
