# Memory hooks register directly in settings.json, not through the group dispatcher

## Question

Issue #4011 needed `user_prompt_submit_memory`, `post_tool_call_memory`, and
`session_end_memory` to actually run. The issue's own PRD comment proposed
adding three `mode: "observe"` groups to `.claude/hooks/dispatch_groups.json`.

## Conventional answer

Follow the `sessionstart-1-context_loader` precedent: put the shim under
`.claude/hooks/<Event>/`, add a group to `dispatch_groups.json`, and register
`invoke_dispatch_claude.py --group <id>` in `.claude/settings.json`.

## First-principles position, checked against the dispatcher

`.claude/lib/claude_hook_dispatch.py` refuses both of the groups the issue
wanted:

- `_MODE_BY_EVENT` (line 90) maps `UserPromptSubmit` to `gate_all`, and
  `validate_group` raises `group event 'UserPromptSubmit' requires mode
  'gate_all'` for anything else. `observe` is rejected outright.
- `_MODE_BY_EVENT` has no `SessionEnd` key at all, so `validate_group` raises
  `group event 'SessionEnd' has no reviewed dispatch mode`.

Routing the memory hooks through the dispatcher therefore means editing the
reviewed mode map in a shared lib plus its byte-identical Copilot mirror. That
is a hook-contract change, not a registration.

Two direct registrations already exist in `.claude/settings.json`
(`PostToolUse/invoke_observation_sync.py`, `PreCompact/invoke_compact_checkpoint.py`),
so direct is an established shape, not a workaround.

## Decision

Three invokers under `.claude/hooks/{UserPromptSubmit,PostToolUse,SessionEnd}/`,
each registered directly in `.claude/settings.json`. `dispatch_groups.json` and
`.claude/hooks/hooks.json` are untouched, so no Copilot hook regeneration and no
`generate_hooks_events.py` run. The invokers put `<repo>/scripts` on `sys.path`
and no-op on `ImportError`, because `scripts/memory_enhancement/` sits outside
every plugin root and never reaches a consumer.

## The exit-code trap that made this more than wiring

Exit 2 is not "guidance available" on every event:

| Event | Channel to the model | Exit 2 means |
|-------|----------------------|--------------|
| PreToolUse | stderr on exit 2 | blocks the tool call |
| PostToolUse | stderr on exit 2 | shows stderr to the model, tool already ran |
| UserPromptSubmit | stdout on exit 0 | blocks the prompt and erases it |
| SessionEnd | none | shows stderr to the user only |

The recall hook returned 2 on every match. Registering it unchanged would have
erased the user's prompt on every turn a memory matched. It now writes to stdout
and returns 0. The reflection hook also returned 2; SessionEnd cannot inject, so
it returns 0 and its value is the confidence scores `reinforce_memories`
persists.

Also: `post_tool_call_memory` read `data["result"]`. Claude Code sends the output
under `tool_response`. The hook was inert against a real payload until that was
fixed.

Related: `mem:pr-3284-memory-hook-bundling`, `mem:decision-claude-hook-group-dispatch`
