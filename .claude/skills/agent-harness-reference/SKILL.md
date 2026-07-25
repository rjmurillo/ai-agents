---
name: agent-harness-reference
description: Field reference for Claude Code and GitHub Copilot CLI hook contracts. Covers hook locations, events, matchers, payloads, decisions, exit codes, timeouts, plugin roots, and cloud limits with official URLs and versioned probes. Use for `harness contract`, `copilot cli hook behavior`, `hook payload format`, `stale plugin root`, `Errno 2 _dispatch.py`, or before changing cross-harness hooks. Do NOT use to run the porting campaign (use `ai-agents-portability-campaign`).
version: 1.1.0
license: MIT
---

# Agent Harness Reference

Use this reference before changing a hook, dispatcher, generator, hook config,
or runtime test. Do not repeat web research unless the refresh rules below say
the recorded contract is stale.

## Triggers

- `harness contract`
- `copilot cli hook behavior`
- `hook payload format`
- `cross-harness hook change`
- `refresh hook evidence`

## Process

1. Read `references/official-hook-contracts.md` for the authoritative row.
2. Read `references/probe-evidence.md` only for versioned runtime evidence.
3. Apply the repository policy in this file and the cited ADRs.
4. If a refresh condition applies, update sources, probes, tests, mirrors, and
   memory in the same change.
5. Mark an absent official answer `DOCS SILENT`. Do not infer it from Claude.

## Authority Order

1. `references/official-hook-contracts.md` records current official sources,
   pinned source commits, exact event sets, output fields, and docs gaps.
2. This file states the repository decisions derived from those contracts.
3. `references/probe-evidence.md` records versioned runtime observations.
4. ADR-068 and ADR-071 record the dispatcher and runtime verification choices.
5. Serena memories are retrieval aids. They do not override the sources above.

If two sources disagree, use the official contract for authored behavior. Keep
the conflicting probe as versioned evidence. Do not erase either side.

## Repository Loading Surfaces

The repository keeps one canonical skill tree and one generated Copilot tree:

- `.claude/skills/agent-harness-reference/` owns this contract.
- `src/copilot-cli/skills/agent-harness-reference/` is generated from it.
- `.github/skills/` is not a repository shipping surface. Do not create it to
  mirror this skill.
- `AGENTS.md`, `.claude/agents/AGENTS.md`, `.github/AGENTS.md`,
  `.github/copilot-instructions.md`, `src/AGENTS.md`, and
  `templates/AGENTS.md` route authoring work here.

Individual agent prompts do not copy the vendor contract. Repository
instructions route agents to this skill so one source owns refresh rules,
citations, and docs-silent classifications.

| Dimension | Contract | Grade | Evidence |
|-----------|----------|-------|----------|
| stdin | One JSON object per invocation; PascalCase tool events use snake_case payload fields such as `tool_name` and `tool_input` | OFFICIAL | <https://code.claude.com/docs/en/hooks>; pinned summary in `references/official-hook-contracts.md` |
| Exit 0 | Allow. Plain stdout can become context on context-bearing events; `systemMessage` is an advisory shown to the user | OFFICIAL | <https://code.claude.com/docs/en/hooks> |
| Exit 2 | Block supported actions and surface stderr according to the event contract | OFFICIAL | <https://code.claude.com/docs/en/hooks> |
| JSON decision payload | PreToolUse uses nested `hookSpecificOutput.permissionDecision`; Stop uses top-level `decision: "block"` | OFFICIAL + CODE | <https://code.claude.com/docs/en/hooks>; strict classification in `.claude/lib/claude_hook_protocol.py` |
| Exit codes vs ADR-035 | Claude hooks are exempt from ADR-035 exit-code taxonomy; each event follows the harness contract | CODE | Surviving hook contract in `.claude/hooks/PostToolUse/invoke_markdown_auto_lint.py:10-16` |
| `CLAUDE_PLUGIN_ROOT` | Set by Claude Code to the plugin install dir; cwd is the USER working dir, not the plugin root | EMPIRICAL (Claude Code 2.1.159, session 1873) | ADR-071 "Verified Runtime Contract" section |
| Lib bootstrap | Hooks resolve shared lib via `CLAUDE_PLUGIN_ROOT` when set, else manifest walk-up to `.claude-plugin/plugin.json` | CODE | `.claude/hooks/PostToolUse/invoke_observation_sync.py:36-63` |

## When to Refresh

Do not search the web for a settled row. Refresh only when one condition holds:

- the installed CLI version changed and the row depends on runtime behavior;
- an official URL or pinned source no longer resolves;
- the sidecar marks the field `DOCS SILENT`;
- a real runtime result contradicts the recorded official contract;
- the requested field is absent from both the sidecar and probe evidence.

When refreshing, update the sidecar, probe evidence, affected ADRs, runtime
tests, generated mirrors, and Serena memory in the same change.

## GitHub Copilot CLI Contract

### Locations and schema

Copilot CLI combines hook entries from policy files, repository
`.github/hooks/*.json`, user `$COPILOT_HOME/hooks/*.json`, inline Copilot and
Claude settings, and installed plugins. Cloud agent loads only repository
`.github/hooks/*.json`.

Config files use:

```json
{
  "version": 1,
  "hooks": {
    "preToolUse": [
      {
        "type": "command",
        "bash": "python3 hook.py",
        "powershell": "py -3 hook.py",
        "cwd": ".",
        "env": {},
        "timeoutSec": 30,
        "matcher": "bash"
      }
    ]
  }
}
```

Command entries support `bash`, `powershell`, or `command`; `cwd`; `env`;
`timeout` or `timeoutSec`; and optional `type: "command"`. HTTP hooks and
sessionStart prompt hooks are also supported. See the sidecar for field limits
and cloud restrictions.

### Exact native event set

The exact 14 native events are:

```text
agentStop
errorOccurred
notification
permissionRequest
postToolUse
postToolUseFailure
preCompact
preToolUse
sessionEnd
sessionStart
subagentStart
subagentStop
userPromptSubmitted
userPromptTransformed
```

PascalCase compatibility aliases exist for the shared Open Plugins events used
by this repository. Event casing selects payload casing:

- native camelCase event keys receive camelCase fields;
- PascalCase compatibility keys receive snake_case fields;
- `agentStop` maps to PascalCase `Stop`;
- `userPromptSubmitted` maps to PascalCase `UserPromptSubmit`;
- `Stop` is per-turn completion. `SessionEnd` is process lifecycle.

Current shipped inventory:

- Vendored Claude plugin source, `.claude/hooks/hooks.json`: two registrations
  across PreToolUse and PostToolUse.
- Generated Copilot plugin, `src/copilot-cli/hooks/hooks.json`: two dispatcher
  registrations, one for each active event.
- Local repository settings, `.claude/settings.json`: five registrations across
  SessionStart, PostToolUse, Stop, and PreCompact. These local hooks do not feed
  the vendored Copilot plugin generator.

Repository mapping and dormant adapter policy:

| Claude source | Copilot registration | Policy |
|---|---|---|
| PreToolUse | PreToolUse | Active consolidated gate dispatcher, one source shim |
| PostToolUse | PostToolUse | Active consolidated observe dispatcher, one source shim |
| PermissionRequest | None | Generic approve/deny translation remains tested; test-runner auto-approval is removed |
| SessionStart | None | Supported observe/discard policy if a vendored source registration is added |
| UserPromptSubmit | None | Supported observe/discard policy if a vendored source registration is added |
| PreCompact | None | Supported observe/discard policy if a vendored source registration is added |
| Stop | None | Direct entries if added, one JSON decision per command |
| SubagentStop | SubagentStop | Direct if a source registration is added |
| SessionEnd | SessionEnd | Direct lifecycle event, never a Stop alias |
| PostToolUseFailure | PostToolUseFailure | Supported if a source is added |

Do not rely on `subagentStart` or `subagentStop` from Copilot's built-in
`general-purpose` agent. Current GitHub docs say it emits neither event. Other
built-in YAML agents and custom agents emit them. The 1.0.72-1 probe record has
a conflicting observation; treat that row as unresolved and version-specific.

### Matchers

Matchers are supported. Native event matchers are full-value regular
expressions. PascalCase PreToolUse and PermissionRequest use Claude-compatible
tool-name semantics:

- `*`, `**`, or empty matches every tool;
- a literal or `|` alternation matches exact Claude tool names;
- other patterns are case-sensitive, whole-name regular expressions.

Copilot CLI 1.0.57 and 1.0.58 had matcher bugs. The changelog records the fix,
and 1.0.72-1 selectively fired a PascalCase `Bash` matcher. Keep script-side
self-filtering as defense in depth, not as evidence that the host lacks
matchers.

### PreToolUse decisions

Copilot CLI uses a top-level object:

```json
{
  "permissionDecision": "allow",
  "permissionDecisionReason": "Reason",
  "modifiedArgs": {}
}
```

`permissionDecision` accepts `allow`, `deny`, or `ask`.
`permissionDecisionReason` is required for deny. `modifiedArgs` replaces the
tool arguments.

Do not emit Claude's nested `hookSpecificOutput` envelope to Copilot CLI.
Do not emit top-level `decision: "deny"` for PreToolUse. Copilot documents
`decision` only for Stop and SubagentStop.

### PermissionRequest decisions

Copilot CLI accepts only:

```json
{
  "behavior": "allow",
  "message": "Reason",
  "interrupt": false
}
```

`behavior` accepts only `allow` or `deny`. Claude's canonical `ask` has no
Copilot value. The adapter must emit no stdout so normal permission handling
continues. `behavior: "ask"` is invalid. A 1.0.72-1 noninteractive probe denied
after empty output. That is mode-dependent host behavior, not an empty-output
deny contract.

The repository adapter accepts one complete JSON document regardless of
whitespace or pretty printing. It rejects trailing content after that document.
Translated `approve` and `deny` decisions require a string `reason`; malformed
exit-0 output is diagnosed on stderr and suppressed so the host uses its
documented default flow.

Cloud agent pre-approves tools, so PermissionRequest does not provide a usable
cloud policy gate. Use PreToolUse for cloud enforcement.

### Stop decisions

Stop and SubagentStop use:

```json
{
  "decision": "block",
  "reason": "Continue because..."
}
```

Current Claude Code uses the same top-level `decision: "block"` and `reason`
shape. Shared Stop producers do not need a harness-specific adapter.

`block` forces another turn. Omitting `decision` permits completion. Keep
multiple Stop or SubagentStop hooks as separate registrations unless a
dispatcher implements a real decision merger. Copilot parses one final JSON
document per command hook; concatenating two objects produces malformed output
and discards both.

### Exit, timeout, and malformed-output behavior

| Condition | Copilot behavior |
|---|---|
| PreToolUse exit 0 with allow JSON | Uses JSON decision |
| PreToolUse exit 2 | Denies |
| PreToolUse other nonzero or crash | Denies |
| PermissionRequest exit 2 | Denies |
| Other command-hook nonzero | Logs and fails open |
| Any command-hook timeout | Fails open, including policy PreToolUse |
| Exit 0 with malformed JSON | Ignores output and uses default behavior |
| Empty exit-0 output | No hook decision |

Exit 2 is not a Claude-only blocking convention. Current Copilot docs and
changelog both state that PreToolUse exit 2 denies. Timeouts are the exception:
all command-hook timeouts fail open.

Copilot docs say exit-2 stderr is surfaced to the user in the general case.
PermissionRequest documents stderr as ignored for its exit-2 path. The docs do
not say stderr enters model context.

### Output fields

| Event | Documented config-file output |
|---|---|
| PreToolUse | `permissionDecision`, `permissionDecisionReason`, `modifiedArgs` |
| PostToolUse | `modifiedResult`, `additionalContext` |
| PermissionRequest | `behavior`, `message`, `interrupt` |
| agentStop / subagentStop | `decision`, `reason` |
| notification | `additionalContext` |
| userPromptTransformed | `modifiedTransformedPrompt` |
| SessionStart | `additionalContext` |
| SubagentStart | `additionalContext` |
| PostToolUseFailure exit 2 | stdout becomes `additionalContext` |

`suppressOutput` appears in implementation-only SDK types but not in the
official config-file hook contract. Do not use it in strict plugin hooks.

Copilot parses at most one final JSON document from each command hook. This
constraint applies to every structured output, not only Stop decisions. A
dispatcher that runs several field-producing hooks must merge their documented
fields into one event-valid object, or keep those producers as direct host
registrations. The repository adapter captures plain stdout from successful
PostToolUse observers, preserves registration order, and emits one
`{"additionalContext":"..."}` object. A blank line separates each flat
contribution. Failed-observer partial output is discarded. It emits nothing
when all observers are silent. This text merger does not merge `modifiedResult`
or pre-structured JSON. The Claude grouped dispatcher uses the same
process-level capture boundary before it emits one Claude protocol document.
It treats only event-valid blocking shapes as terminal: `continue: false`;
Stop or SubagentStop `decision: block` with a string reason; or nested
PreToolUse `permissionDecision: deny` with a string reason. Generic JSON with
no protocol keys becomes context and later guards run. Malformed object-shaped
JSON, allow-shaped decisions, unsupported decision fields, and invalid field
types fail closed in gate modes.

SessionStart supports `additionalContext`, but the vendored plugin has no current
SessionStart registration. The tested adapter policy captures Python streams,
direct file-descriptor writes, and inherited child-process output, then discards
the content instead of turning repository text into model instructions.
Copilot documents no config-file output field for PreCompact. It also has no
current vendored source registration. Direct rollback tests preserve lifecycle
side effects while suppressing stdout and stderr at the shell boundary.
PostToolUseFailure also stays direct because exit-2 stdout has host-defined
recovery-context semantics that generic observe mode cannot preserve.

Copilot documents no config-file output field for UserPromptSubmitted, including
its PascalCase UserPromptSubmit compatibility event. No current vendored source
registration exists. The tested dispatcher and direct rollback policies keep its
output out of model context. Whether stderr enters model context is docs silent.
Every unclassified future event remains a direct host registration until its
output and failure semantics are reviewed.

### Cloud agent

Cloud agent loads `.github/hooks/*.json` only, and the file must exist on the
default branch. It runs in an ephemeral Linux sandbox. Only `bash`, or
`command` fallback, executes. Tools are pre-approved. Notification does not
fire. PreCompact fires only for automatic compaction. PreToolUse `ask` becomes
deny because no user can answer.

Installed plugin hooks, user hooks, repository settings, and PowerShell entries
do not reach the cloud agent.

## Copilot Plugin Runtime Fields

Current official hook docs define `cwd` relative to the repository root or as
an absolute path. Do not assume the plugin directory from `cwd`.

The Copilot CLI changelog documents `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT`, and
`CLAUDE_PLUGIN_ROOT` for plugin hooks. The repository keeps the version-tested
fallback:

```bash
${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}
```

The 1.0.57 probe measured all three variables pointing to the installation
directory. Treat the exact aliases as implementation-sensitive. Keep the
runtime test and negative control when changing launcher paths. The 1.0.72-1
probe did not independently measure the effect of generated `cwd: "."`.
Launchers do not rely on it to locate plugin scripts.

### Stale plugin root wedges a running session

Copilot CLI resolves the plugin root once and exports the same value for the
life of the process. Delete or move the plugin install directory mid-session and
every hook invocation fails before any repository code runs, because the shell
expands a path that no longer exists. Signature:

```text
python.exe: can't open file
'...\.copilot\installed-plugins\_direct\project-toolkit/hooks/PreToolUse/_dispatch.py':
[Errno 2] No such file or directory
```

`_direct` in that path is the local development shadow, not the published
install. Every tool call is denied for the rest of the session, including read
tools, because a `PreToolUse` launcher that cannot start its interpreter fails
closed before matcher evaluation.

Remedy: restart the Copilot session. Reinstalling the plugin without restarting
does not help when the root moved, since the exported value does not change.

Do not add an existence check to the launcher command strings. The interpreter
error already names the missing path, so a guard buys only the restart
sentence, and it costs branching logic inside the highest-blast-radius string in
the repository, in a generated artifact, in two shell dialects. This is the same
argument ADR-006 makes against logic in workflow YAML. Evidence: issues #3321
and #3332, GitHub Copilot CLI 1.0.72-1.

## Claude Code Delta

Claude Code is a separate contract:

| Dimension | Claude Code | Copilot CLI |
|---|---|---|
| PreToolUse deny JSON | `hookSpecificOutput.permissionDecision: "deny"` | top-level `permissionDecision: "deny"` |
| Exit 2 | Blocks and sends stderr to Claude | Denies PreToolUse and PermissionRequest; other events continue |
| Matcher | Event-specific exact or regular-expression semantics | Native full-value regex; PascalCase tool aliases use Claude-compatible semantics |
| Per-turn stop | `Stop` | `agentStop` or PascalCase `Stop` |
| Session end | `SessionEnd` | `sessionEnd` or PascalCase `SessionEnd` |
| Event count | 30 documented events | 14 native events |
| Cloud reach | Claude Code local or remote runtime contract | Only default-branch `.github/hooks/*.json` reaches cloud agent |

Claude's current 30-event set and nested PreToolUse output are pinned in the
official sidecar. Never translate fields by name similarity alone.

## Verification

Before changing cross-harness hooks:

- [ ] Read `references/official-hook-contracts.md`.
- [ ] Classify each claim as official, empirical, or docs silent.
- [ ] Preserve PascalCase event keys where snake_case payloads are required.
- [ ] Keep Stop separate unless output merging has a negative-control test.
- [ ] Keep any multi-producer structured output separate unless an
      event-specific merger has positive, negative, and edge tests.
- [ ] Route PostToolUse text through one `additionalContext`.
- [ ] Discard SessionStart and PreCompact repository prose unless a reviewed
      trust boundary makes it safe model context.
- [ ] Capture Python streams, file descriptors 1 and 2, and inherited child
      output on both channels where lifecycle prose is discarded.
- [ ] Treat unknown Claude JSON as context, never as a terminal gate decision.
- [ ] Accept only event-valid Claude blocking shapes as terminal. Fail closed
      on malformed, allow-shaped, unsupported, or invalid typed decisions.
- [ ] Reject empty, malformed, event/mode-mismatched, or path-escaping Claude
      dispatch groups before any shim runs.
- [ ] Keep PostToolUseFailure direct unless an event-specific merger preserves
      exit-2 recovery context.
- [ ] Keep UserPromptSubmit stdout and stderr out of host channels unless the
      host documents a model-context output field.
- [ ] Keep unclassified events direct until their host contracts are reviewed.
- [ ] Keep PermissionRequest `ask` silent.
- [ ] Run generator tests and committed-artifact tests.
- [ ] Run the real target CLI when the change affects runtime-only behavior.
- [ ] Regenerate `.github` and `src/copilot-cli` mirrors from canonical
      `.claude` sources.

## Anti-Patterns

- Treating a runtime probe as a stable vendor contract.
- Copying Claude output fields or exit semantics into Copilot adapters.
- Mapping per-turn `Stop` behavior onto process-lifecycle `SessionEnd`.
- Citing Serena memory when the official sidecar owns the answer.

## Extension Points

Add a contract row when a harness adds an event, payload field, decision shape,
or loading surface. Pin the official source, add a versioned probe when
documentation is silent, then update the adapter tests and generated mirrors.

## Provenance and Maintenance

Verified 2026-07-22. Official citations, access dates, and commit-pinned vendor
sources live in `references/official-hook-contracts.md`. Version-scoped probes
and negative results live in `references/probe-evidence.md`. ADR-071 owns the
plugin-root and launcher contract. ADR-068 owns dispatcher economics.

Refresh this reference when either host changes its hook documentation, event
set, payload schema, exit semantics, matcher behavior, timeout behavior, or
cloud loading rules. Re-run the applicable recipes in
`ai-agents-empirical-probe-toolkit`, update both reference files, amend affected
ADRs, refresh Serena memories, regenerate Copilot mirrors, and run
`tests/build_scripts/test_hook_contract_knowledge.py`.

## Vendored Use

<!-- vendor-portability: .agents/ and .serena/ paths below are upstream maintainer provenance only. Vendored consumers use this skill's bundled references/ sidecars and do not require those repository trees (issue #2050). -->

The operational contract and refresh procedure ship in this skill's
`references/` directory. The upstream repository paths below preserve decision
history for maintainers. Their absence in a consumer repository does not change
skill behavior.

## Related

- ADR-071 `.agents/architecture/ADR-071-plugin-hook-runtime-contract-verification.md` (Verified Runtime Contract: Copilot 1.0.57, Claude Code 2.1.159, env dump quote); status Accepted 2026-06-02
- ADR-068 `.agents/architecture/ADR-068-consolidated-hook-dispatcher.md` (historical matcher incident, process kill, and cold-start evidence); status Accepted
- `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md` (probe evidence, docs wrong by omission)
- `.serena/memories/copilot-hooks-observations.md` (payload casing, exit 143, toolArgs JSON string)
- `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md` and `2026-06-02-issue-2290-copilot-hook-payload-format.md`
- `build/scripts/generate_hooks_emit.py:335-421`; `build/scripts/generate_hooks_events.py:381-385`; `templates/platforms/copilot-cli.yaml:52-62`
- `.claude/rules/generated-artifacts.md`; `.claude/rules/lsp-first.md`; `.claude/rules/claude-agents.md` (MUST 2)
- `.claude/lib/claude_hook_protocol.py`; `.claude/lib/hook_dispatch_protocol.py`
- Manifests and `.mcp.json` read directly 2026-07-03

- `ai-agents-portability-campaign`: execute a contract change.
- `ai-agents-empirical-probe-toolkit`: probe a missing or disputed row.
- `ai-agents-generation-and-release`: regenerate and release mirrors.
- ADR-068: dispatcher boundaries and direct decision events.
- ADR-071: runtime-contract verification.
