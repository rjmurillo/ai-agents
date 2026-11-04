## Matters

- Generated from `templates/hooks/`; edit the template, not this tree. Render map: `templates/AGENTS.md`.
- Hand-maintained exceptions: `AGENTS.md`, five `CLAUDE.md`, `PostToolUse/README.md`.
- Group dispatcher only on `SessionStart`; `UserPromptSubmit`, `Stop`, `SessionEnd`, `PreCompact` register directly.
- `hooks.json` (`src/claude/hooks/hooks.json`, linked here) registers one plugin hook: the advisory Stop group `plugin-stop-1-reflect_nudge` (ADR-084 rule 2a). This checkout pins the plugin off, so its live registrations come from `.claude/settings.json`.
- `PreToolUse`/`PostToolUse` ship no Python hook, only a bootstrap helper.
- `invoke_memory_recall.py`/`invoke_memory_reflection.py` call a package outside the plugin root; consumer installs no-op silently.
