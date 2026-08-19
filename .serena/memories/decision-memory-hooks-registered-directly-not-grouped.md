# Memory hooks register directly in settings.json, not through the group dispatcher

> **PARTIALLY SUPERSEDED 2026-08-19 by ADR-096.** Two of the three hooks this
> record covers are retired: `post_tool_call_memory` (via its
> `invoke_memory_capture.py` wrapper, and the module itself) and
> `invoke_observation_sync.py`. `user_prompt_submit_memory` and
> `session_end_memory` still register directly in `.claude/settings.json`, so
> the decision below still holds for them. The reasoning about direct
> registration versus the group dispatcher is unchanged; only the inventory
> shrank.

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
it returns 0 and the health summary on stderr is its whole output.

## Registration turns a dormant writer into a live one

`reinforce_memories` round-tripped every memory through `save_memory` to persist
a confidence score. Nothing had ever called it outside pytest. Registering the
SessionEnd hook made the first real session end rewrite 879 tracked files and
delete 828 lines of `## Links` cross-references. The write also bought nothing:
confidence is a pure function of citation validity, age, recency, and link
count, recomputed on every read in `search._score_memory_file`, and no reader
consumed the stored value. It is gone; the hook scores and reports.

Before registering a dormant code path, ask what it writes and how many files it
touches on its first live run. A test corpus of one file cannot answer that.

Also: `post_tool_call_memory` read `data["result"]`. Claude Code sends the output
under `tool_response`. The hook was inert against a real payload until that was
fixed. Its success path then fired on any output containing `.py` or `.md`, so
roughly 40% of ordinary tool calls injected an empty suggestion; only failures
are worth an interrupt.

## The registered interpreter is part of the contract

`settings.json` says `python3`. Every pre-existing hook there is stdlib-only, so
that worked. Recall and reflection import `python-frontmatter`, which lives only
in the uv virtualenv, so both exited 0 having done nothing while
`tests/test_memory_hook_registration.py` passed green against `sys.executable`.
`memory_enhancement.interpreter` re-execs under `.venv`, and the test now launches
the command settings.json names with `VIRTUAL_ENV` stripped from `PATH`.

Related: `mem:pr-3284-memory-hook-bundling`, `mem:decision-claude-hook-group-dispatch`
