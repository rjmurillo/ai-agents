## Matters

- Generated from `templates/hooks/`; edit the template, not this tree. Render map: `templates/AGENTS.md`. Shipped entries pass through `src/claude/hooks/`; the repo-only entries (`PreCompact`, `PreToolUse`, `SessionEnd`, `SessionStart`, `UserPromptSubmit`, `session-start.sh`, the `hooks` row's `repo_only` list) render straight here and ship in no plugin.
- Hand-maintained exceptions: `AGENTS.md`, five `CLAUDE.md`, `PostToolUse/README.md`.
- Group dispatcher only on `SessionStart`; `UserPromptSubmit`, `Stop`, `SessionEnd`, `PreCompact` register directly.
- `hooks.json` links to `src/claude/hooks/hooks.json`: one advisory Stop group. Live registrations here are `.claude/settings.json`.
- `PreToolUse`/`PostToolUse` ship no Python hook, only a bootstrap helper.
- `invoke_memory_recall.py`/`invoke_memory_reflection.py` call a package outside the plugin root; consumer installs no-op silently.
