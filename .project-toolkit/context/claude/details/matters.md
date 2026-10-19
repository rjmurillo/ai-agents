## Matters

- Generated, never hand-edit: `agents/`, `rules/`, `skills/<name>/SKILL.md`, `hooks/`, `settings.json`, `lib/` packages plus `lib/bootstrap.py`. Sources: `templates/` and the `scripts/` packages of `rjmurillo/ai-agents`.
- Hand-maintained here: `lib/` (mixed, see next line), `CLAUDE.md`, this guide, the seven doc files under `hooks/`, repo-local skills' non-`SKILL.md` files. No manifest: `.claude-plugin/plugin.json` was deleted at B6.
- `lib/` mixed: `ai_review_common/`, `github_core/`, `hook_utilities/`, `bootstrap.py`, `paths.py` link into `src/claude/lib/` (ADR-119); edit there. Other top-level modules (`claude_hook_dispatch.py`, siblings) are real files edited here.
