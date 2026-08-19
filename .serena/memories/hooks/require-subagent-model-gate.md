# require-subagent-model gate (issue #4874)

> **SUPERSEDED 2026-08-19 by ADR-096.** This gate is retired. The script
> `.claude/hooks/PreToolUse/invoke_require_subagent_model.py`, its dispatch
> group `plugin-pretooluse-10-require_subagent_model`, and the Copilot surface
> `.github/hooks/require-subagent-model.json` are all deleted, along with every
> other tool-call hook. Nothing enforces the call-time arm now;
> `scripts/validation/check_model_pins.py` still covers the definition-file arm.
> The cross-harness payload facts below remain accurate and are the reason this
> record is kept rather than deleted: they were expensive to derive and a future
> re-add would need them again. Do not read anything here as describing a live
> registration.

PreToolUse gate denying sub-agent spawns that name no model and resolve no
agent definition file. Canonical script
`.claude/hooks/PreToolUse/invoke_require_subagent_model.py`, dispatch group
`plugin-pretooluse-10-require_subagent_model`, matcher `^(Agent|Task)$`,
Copilot repo surface `.github/hooks/require-subagent-model.json` (native
`preToolUse`, matcher `task`). Escape hatch: `CLAUDE_CODE_SUBAGENT_MODEL`.

## Cross-harness facts worth not re-deriving

- Copilot CLI's subagent spawn is runtime tool `task`; the hooks reference maps
  it to Claude tool name `Agent` ("the literal `Task` is also accepted").
  PascalCase `PreToolUse` registrations therefore see `tool_name: "Agent"`.
- Copilot `task` args carry `agent_type` AND optional `model` (observed in a
  real session log, CLI 1.0.79, 2026-08-06, `~/.copilot/session-state/*/events.jsonl`
  `toolRequests`). Claude's `Agent` tool uses `subagent_type` and `model`.
- Claude Code enforcement runs through the installed plugin dispatcher
  (`.claude/hooks/hooks.json`, group `plugin-pretooluse-10-require_subagent_model`).
  Copilot enforcement runs through the native `.github/hooks` registration.
  There is no `.claude/settings.json` PreToolUse entry; the parity test
  explicitly requires the twin to remain absent.
- Read stdin through 2 MiB plus one byte. Parse complete bounded payloads and
  deny overflow. A smaller read can truncate valid JSON and reach the
  malformed-input fail-open path.
- For Claude payloads, prefer `CLAUDE_PROJECT_DIR` over payload `cwd`, which
  may be a project subdirectory. Copilot uses process cwd (repository root
  by contract); `CLAUDE_PROJECT_DIR` is never consulted for Copilot payloads.
  For namespaced agents, check active `CLAUDE_PLUGIN_ROOT` and
  `COPILOT_PLUGIN_ROOT` directories only when the plugin manifest name matches
  the requested namespace.
- Reject unsafe agent and namespace path segments, including glob characters,
  separators, control characters, extra colons, and `.` or `..`.
- Committing ADR metric edits requires: session log staged in the same commit
  (session-policy) plus a debate log in `.agents/critique/*debate*.md`
  referencing the staged ADR IDs (adr-review-policy in
  `scripts/validation/git_hook_policy.py`).
- `test_hook_contract_knowledge.py` pins hook registration counts in THREE
  prose forms ("N events, M groups", "N events and M groups", "N events / M
  groups") across `ai-agents-architecture-contract` (SKILL.md and
  `references/provenance.md`), `ai-agents-config-catalog`, ADR-068, ADR-071,
  and ADR-085. A new dispatch group touches all of them.

## Why

Sub-agents with no definition file silently inherit the session model; on a
Fable/Opus session every general-purpose spawn runs at session-model price.

## How to apply

Adding another plugin gate: script under `.claude/hooks/PreToolUse/`, group in
`dispatch_groups.json`, hand-add the hooks.json dispatcher entry (clone the
launcher boilerplate, swap the group id), regenerate with
`uv run python build/scripts/build_all.py --platform copilot-cli`, add the
AUTHORIZED_HOOKS ledger entry, then chase the knowledge-test count pins.
