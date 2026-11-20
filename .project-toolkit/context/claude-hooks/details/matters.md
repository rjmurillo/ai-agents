## Matters

- Generated from `templates/hooks/`; edit the template, not this tree. Render map: `templates/AGENTS.md`. The `hooks` row's `repo_only` entries render here directly.
- Hand-maintained exceptions: `AGENTS.md`, five `CLAUDE.md`, `PostToolUse/README.md`.
- Group dispatcher only on `SessionStart`; `UserPromptSubmit`, `Stop`, `SessionEnd`, `PreCompact` register directly.
- `hooks.json` links to `src/claude/hooks/hooks.json`: advisory Stop group, `UserPromptSubmit` recall group. Live: `.claude/settings.json`.
- `PreToolUse`/`PostToolUse` ship no Python hook, only a bootstrap helper.
- `invoke_memory_recall.py` ships on the plugin `lib/`; `invoke_memory_reflection.py` needs `scripts/` and does not.
