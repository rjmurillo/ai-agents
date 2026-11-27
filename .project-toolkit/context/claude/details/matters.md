## Matters

- Generated, never hand-edit: `agents/`, `rules/`, `skills/<name>/SKILL.md`, `hooks/`, `settings.json`, `lib/` packages plus `lib/bootstrap.py`. Sources: `templates/` and the `scripts/` packages of `rjmurillo/ai-agents`.
- Hand-maintained here: `lib/` (mixed, see next line), `CLAUDE.md`, this guide, the seven doc files under `hooks/`, repo-local skills' non-`SKILL.md` files. No manifest: `.claude-plugin/plugin.json` was deleted at B6.
- `lib/` mixed: packages, `bootstrap.py`, `paths.py`, `ptk_run.py` link into `src/claude/lib/` (ADR-119). Edit packages and `bootstrap.py` in `scripts/<pkg>/`, the other two in `src/claude/lib/`. Dispatch modules (`claude_hook_dispatch.py`, siblings) are real files edited here; the build copies them into `src/claude/lib/`.
