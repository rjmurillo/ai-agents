## Constraints

- A hand edit here is overwritten by the next build and fails the pre-PR row `Generated Artifact Staleness` (`build_all.py --check`); `Hook Template Drift` covers `src/claude/hooks/` and `.claude/settings.json` only.
- New `PreToolUse`, `PostToolUse`, `PermissionRequest`, `PostToolUseFailure` registration: clear every MUST in `tool-use-hook-bar.md`.
- `validate_group()` pins mode by event, never chosen: `PreToolUse` `gate`, stops at the first block; `UserPromptSubmit`/`Stop`/`SubagentStop` `gate_all`, runs all, exits first block else first non-zero; `PostToolUse`/`SessionStart`/`PreCompact` `observe`, runs all, exits 0, suppresses blocks. Any other event, `SessionEnd` included, exits 2 on every fire.
- `invoke_dispatch_claude.py` exits 0 on a `.claude/lib` import failure, and in non-gate modes when the installed plugin runs inside this checkout (double-fire guard); bad manifest or dispatch exception exits 2, fail-closed.
- A `dispatch_groups.json` shim path must be a `.py` file strictly inside this directory: no `..`, absolute path, or backslash.
- `timeout` 1 to 300s, checked per shim, never enforced at runtime. A shim on a blocking event (`PreToolUse`, `PermissionRequest`, `Stop`, `SubagentStop`, `UserPromptSubmit`) must carry `exit code` or `block` in its first 30 lines. `session-start.sh` escapes both at 900s because the hook-contract check parses Python commands only.
- Only a strictly validated per-event stdout shape blocks (`claude_hook_protocol.py`); other decision-shaped JSON is suppressed in `observe`, denies in the gate modes.
