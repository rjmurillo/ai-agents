# Native Tool Calls Per Host

A skill body runs on many hosts. When it tells the model to call a tool, the
model needs that host's real tool name. A Claude Code name sent to Codex
points the model at a tool that does not exist there.

## Rules

1. **Name the host on the same line as its tool.** Write
   "Claude Code `AskUserQuestion`; Codex `request_user_input`", not a bare
   `AskUserQuestion`. A per-line scanner can then see that the name is
   attributed.
2. **Cover the hosts the user runs, then give a fallback.** At minimum name
   T3 Code, Claude Code, Codex, and Copilot CLI. Name Muse Code, Antigravity,
   Devin, and Factory Droid where a primary source documents the tool. End
   with what to do on any other host (run it yourself, ask in plain chat, run
   one long foreground command).
3. **Cite a primary source, or name no tool.** Use official docs or the
   host's source repository. A forum post, a leaked prompt, or a third-party
   wrapper is not a source. When no source exists, write the fallback only.
4. **Gate optional host tools on presence.** Write "when `watch_pull_request`
   is available", not "in T3 Code, call it". A host may run several providers
   with different catalogs.
5. **Reuse one paragraph per operation.** Do not restate a host table in
   each skill. In the `rjmurillo/ai-agents` repository, render the shared
   partials under `templates/skills/partials/`: `host-delegation` (spawn a
   subagent), `host-ask` (ask the user), and `host-wait` (wait on a
   long-running command). Add a new partial when a new operation needs one.

## Operations and verified tool names

Checked 2026-11-16 against the sources below. Recheck a row before you
change it.

| Operation | Claude Code | T3 Code | Codex | Copilot CLI | Others |
|---|---|---|---|---|---|
| Spawn a subagent | `Agent` (`Task`) | `delegate_task` | `spawn_agent` | `task` | Muse Code `subagent_spawn`; Devin `run_subagent`; Antigravity `invoke_subagent`; Factory Droid `Task` |
| Ask the user | `AskUserQuestion` | provider's question tool | `request_user_input` (Plan mode) | `ask_user` | Muse Code `request_user_input`; Devin `ask_user_question`; Factory Droid `AskUser` |
| Run a shell command | `Bash` / `PowerShell` | provider's terminal tool | `exec_command` | `bash` / `powershell` | Devin `exec`; Antigravity `run_command`; Factory Droid `Execute` |
| Wait on a background command | `Bash` `run_in_background`, then `Monitor` | `t3_background_wait` | `write_stdin` with empty `chars` | `read_bash` / `read_powershell` | Devin `get_output`; Muse Code: none documented |
| Watch a pull request | none | `watch_pull_request`, `unwatch_pull_request` | none | none | none documented |
| Load a skill | `Skill` | provider's skill tool | read the `SKILL.md` | `skill` | host docs |

Sources:

- Claude Code: <https://code.claude.com/docs/en/tools-reference>
- Codex: <https://github.com/openai/codex/tree/main/codex-rs/core/src/tools/handlers>
- Copilot CLI: <https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference>
- Devin CLI: <https://docs.devin.ai/cli/subagents.md>
- Antigravity: <https://antigravity.google/docs/hooks/>
- Factory Droid: <https://docs.factory.ai/reference/hooks-reference>
- T3 Code: the live tool catalog of the session.

## Review check

Before Phase 4, grep the generated body for each tool name in the table. Each
hit must name its host on the same line, or sit inside a shared host
paragraph. A bare name is a finding.
