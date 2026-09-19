## Matters

- Generated from `templates/hooks/`; edit the template, not this tree. Render map: `templates/AGENTS.md`.
- Hand-maintained exceptions: `AGENTS.md`, five `CLAUDE.md`, `PostToolUse/README.md`.
- Group dispatcher only on `SessionStart`; `UserPromptSubmit`, `SessionEnd`, `PreCompact` register directly.
- `hooks.json` declares `"hooks": {}`: the shipped `project-toolkit` copy (`src/claude/hooks.json`, of which this is the binplace) registers nothing. Every live registration is `.claude/settings.json`.
- `PreToolUse`/`PostToolUse` ship no Python hook, only a bootstrap helper and a markdownlint config.
- `invoke_memory_recall.py`/`invoke_memory_reflection.py` call a package outside the plugin root; consumer installs no-op silently.
