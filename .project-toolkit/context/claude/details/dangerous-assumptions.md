## Dangerous assumptions

- "`rules/`, `agents/`, `skills/<name>/SKILL.md`, `hooks/`, `settings.json`, `lib/` packages are hand-authored" is false since ADR-109 B1 to B5; `generated-artifacts.md` auto-loads for all but `settings.json`.
- "A hook wired in `settings.json` ships to plugin consumers" is false; see `.claude/hooks/AGENTS.md`.
- "This guide loads like `CLAUDE.md`" is false: on demand, never passively budgeted.
