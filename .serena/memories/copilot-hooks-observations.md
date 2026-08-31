# GitHub Copilot CLI Hook Contract

Last updated: 2026-07-20

## Retrieval route

Use `.claude/skills/agent-harness-reference/SKILL.md` for implementation.
Official and pinned sources live in
`.claude/skills/agent-harness-reference/references/official-hook-contracts.md`.
Versioned observations live in the adjacent `probe-evidence.md`.

Do not repeat web research unless the reference skill's refresh rules apply.

## Current official contract

- Copilot CLI has 14 native events. Stop is the per-turn `agentStop` alias.
  SessionEnd is separate process lifecycle.
- SubagentStop, PermissionRequest, and PreCompact are supported.
- Native matchers are anchored full-value regexes. PascalCase PreToolUse and
  PermissionRequest use Claude-compatible tool names.
- PreToolUse decisions use top-level `permissionDecision`,
  `permissionDecisionReason`, and `modifiedArgs`.
- PermissionRequest uses `behavior: "allow"|"deny"`, `message`, and
  `interrupt`. There is no `ask` behavior. A translated Claude ask emits no
  stdout and lets normal permission handling continue.
- PreToolUse nonzero exits deny. PermissionRequest exit 2 denies. Other
  command-hook failures fail open. Every command-hook timeout fails open.
- Exit-0 malformed JSON is ignored. Copilot parses one final JSON document per
  hook, so two concatenated decision objects are both lost.
- SessionStart and PostToolUse document `additionalContext`. PreCompact and
  UserPromptSubmitted document no config-file output field. Whether exit-0
  stderr enters model context remains docs silent.
- Cloud agent loads only default-branch `.github/hooks/*.json`. It does not
  load installed plugins or settings files.
- The official changelog documents `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT`, and
  `CLAUDE_PLUGIN_ROOT` for plugin hooks.

## Repository decisions

- Use PascalCase registrations for source hooks that expect snake_case input.
- Keep script-side matcher filtering as defense in depth.
- Keep Stop and SubagentStop as separate host registrations unless a tested
  merger produces one valid decision object.
- Map PreCompact to PreCompact.
- Never map Stop to SessionEnd.
- Keep the version-tested Copilot root fallback in generated launchers.
- Merge plaintext from successful PostToolUse observers into one ordered, flat
  `additionalContext` string. Discard partial stdout from failed observers.
- Capture SessionStart and PreCompact Python stdout and stderr, direct writes to
  file descriptors 1 and 2, and inherited child-process output on both channels.
  Discard the content because current producers load branch-controlled session
  state. Do not turn repository text into model instructions.
- Claude groups fail closed on empty or malformed manifests, event/mode mismatch,
  duplicate or escaping shim paths, path-resolution errors, and unknown events.
  Unknown JSON is context and cannot skip a later gate. Only event-valid
  blockers terminate a gate. Malformed object-shaped JSON, allow-shaped
  decisions, unsupported fields, and invalid field types fail closed.
- Keep direct SessionStart and PreCompact rollback commands silent on stdout and
  stderr while retaining producer side effects.
- Keep PostToolUseFailure direct because exit-2 stdout becomes recovery context.
  Any producer that emits untrusted content requires security review.
- Redirect successful UserPromptSubmit stdout to stderr in dispatcher and direct
  rollback modes. Do not invent an output field or depend on stderr reaching
  model context.
- Keep every unclassified event direct until its output and failure contracts
  are reviewed. Never default an unknown event to observe mode.
- Current PostToolUse producers are plaintext diagnostics. A producer of
  `modifiedResult` or pre-structured JSON requires a field-specific merger or a
  direct host registration.

## Repository loading surfaces

- `.claude/skills/agent-harness-reference/` is canonical.
- `src/copilot-cli/skills/agent-harness-reference/` is generated.
- `.github/skills/` is not a shipping surface in this repository. Do not create
  it as another mirror.
- Authoring routes live in `AGENTS.md`, `.claude/agents/AGENTS.md`,
  `.github/AGENTS.md`, `.github/copilot-instructions.md`, `src/AGENTS.md`, and
  `templates/AGENTS.md`.
- Contract changes run through `ai-agents-portability-campaign`.
- Do not copy current plugin versions into guidance. Read each
  `.claude-plugin/plugin.json` when executing the version-bump gate.

## Versioned discrepancies

- Copilot CLI 1.0.57 and 1.0.58 had matcher defects. Current docs and 1.0.72-1
  show selective matcher firing.
- A 1.0.72-1 probe saw SubagentStop after a child selected as
  `general-purpose`. Current docs say the built-in general-purpose agent emits
  neither subagent event. Do not depend on that observation.
- In Copilot CLI 1.0.72-1, interactive `/compact` completed but did not emit
  PreCompact. The generated dispatcher wrote a checkpoint when invoked directly
  under the same plugin contract. Manual compaction is a negative control;
  automatic-compaction delivery remains unmeasured.

## Installed-plugin E2E safety

- [2026-07-20] [Copilot CLI 1.0.72-1 probe]: Run
  `test_installed_plugin_hook_e2e.py` with both `HOME` and `COPILOT_HOME`
  pointed at one isolated directory. Register the repository root as the local
  `ai-agents` marketplace, then install `project-toolkit@ai-agents`.
- [2026-07-20] [Copilot CLI 1.0.72-1 probe]: An unqualified
  `copilot plugin uninstall project-toolkit` removed the marketplace
  registration but left the `_direct/project-toolkit` cache. The active session
  then lost its hook scripts and denied matching tools until the marketplace
  plugin was restored.
- [2026-07-20] [test:tests/e2e/test_installed_plugin_hook_e2e.py]: The isolated
  marketplace install passed all 9 installed-tree tests from a foreign working
  directory. The positive matcher test must accept anchored tool-only regexes
  such as `^(Write|Edit)$`; assuming a bare matcher skips every current
  positive case.

## Related memories

- `decision-copilot-cli-hook-plugin-root-contract.md`
- `copilot-hook-generation-invariants.md`
- `decision-claude-hook-group-dispatch.md`
