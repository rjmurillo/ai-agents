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
| Exit codes vs ADR-035 | Claude hooks are exempt from ADR-035 exit-code taxonomy; each event follows the harness contract | CODE | Surviving hook contract in `.claude/hooks/SessionStart/invoke_context_loader.py` (the `invoke_observation_sync.py` citation was retired with that hook by ADR-097) |
| `CLAUDE_PLUGIN_ROOT` | Set by Claude Code to the plugin install dir; cwd is the USER working dir, not the plugin root | EMPIRICAL (Claude Code 2.1.159, session 1873) | ADR-071 "Verified Runtime Contract" section |
| Lib bootstrap | Hooks resolve shared lib via `CLAUDE_PLUGIN_ROOT` when set; otherwise a fixed relative parent-walk (`Path(__file__).resolve().parents[N] / "lib"`), not a search for `.claude-plugin/plugin.json` | CODE | `.claude/hooks/SessionStart/invoke_context_loader.py:38-45` (the `invoke_observation_sync.py` citation was retired with that hook by ADR-097) |
| `CLAUDE_PROJECT_DIR` under Copilot CLI | Not exported. Copilot loads `.claude/settings.json` hooks but never sets this variable, so a bare `cd "$CLAUDE_PROJECT_DIR"` anchor is `cd ""`, a silent no-op. Anchor with `${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}` | EMPIRICAL (Copilot CLI 1.0.80, issue #4727) | `references/probe-evidence.md` section 8b |
| `COPILOT_CLI` | Set to `1` for subprocesses Copilot CLI spawns; the documented way a hook detects it is running under Copilot | OFFICIAL | Vendor `changelog.json` shipped in the `@github/copilot` package, version `0.0.421`; quoted in `references/official-hook-contracts.md` |
| `CLAUDE_CODE_ENTRYPOINT` | Set by Claude Code, absent from the Copilot CLI build measured. Use it, not `COPILOT_CLI` alone, to identify the consuming host: Copilot exports `COPILOT_CLI` into every shell it spawns, so a Claude session started underneath one inherits it | EMPIRICAL (Copilot CLI 1.0.80 and Claude Code, issue #4727) | `references/probe-evidence.md` section 8b |

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

The full vendor inventory for this harness lives in `references/official-hook-contracts.md`,
with the official source cited per row: the configuration schema, the 14 native
events and their PascalCase aliases, matcher targets and compiled semantics, the
PreToolUse, PermissionRequest and Stop output shapes, the exit-code and timeout
table, the per-event output fields, the `DOCS SILENT` rows, and the cloud agent
restrictions. Read that file for the contract. This section records what this
repository decided on top of it, plus the two facts repeated below because
they are the ones most often guessed wrong.

PreToolUse output is a top-level `permissionDecision`, never Claude's
nested `hookSpecificOutput` envelope and never a top-level `decision`. Exit 2
does not deny everywhere: it warns and continues by default, and denies only for
PreToolUse and PermissionRequest. Where exit 2 does deny, a timeout still does
not. Timeouts fail open on every event, including policy PreToolUse, so a gate
that hangs is a gate that passes the call through.

### Shipped registrations

Re-verified 2026-08-19 against the tree, not carried forward from a prior count:

- Vendored Claude plugin source, `.claude/hooks/hooks.json`: zero registrations
  (ADR-097 retired all four).
- Generated Copilot plugin, `src/copilot-cli/hooks/hooks.json`: zero
  registrations (ADR-097 retired the dispatcher itself; no `_dispatch.py`
  ships).
- Local repository settings, `.claude/settings.json`: six registrations across
  four events, SessionStart (3), UserPromptSubmit (1), SessionEnd (1), and
  PreCompact (1). ADR-097 retired the two repo-local per-call registrations
  this file used to carry (PostToolUse `observation_sync`, PostToolUseFailure
  `memory_capture`).
  These do not feed the vendored Copilot plugin generator.

### Event policy

Every per-call row below describes retired machinery (ADR-097): no source
registration exists on either harness today, so "None" everywhere in the
Copilot-registration column reflects the current, not the historical, state.
A future re-add must clear `.claude/rules/tool-use-hook-bar.md` first and
rebuild the policy this table records, not inherit it.

| Claude source | Copilot registration | Policy |
|---|---|---|
| PreToolUse | None | Retired (ADR-097): the consolidated gate dispatcher and its one source shim are deleted; a re-add rebuilds both from scratch |
| PostToolUse | None | Retired (ADR-097): the consolidated observe dispatcher and its one source shim are deleted; a re-add rebuilds both from scratch |
| PermissionRequest | None | Generic approve/deny translation stays tested; test-runner auto-approval is removed |
| SessionStart | None | Supported observe/discard policy if a vendored source registration is added |
| UserPromptSubmit | None | Supported observe/discard policy if a vendored source registration is added |
| PreCompact | None | Supported observe/discard policy if a vendored source registration is added |
| Stop | None | Direct entries if added, one JSON decision per command |
| SubagentStop | SubagentStop | Direct if a source registration is added |
| SessionEnd | SessionEnd | Direct lifecycle event, never a Stop alias |
| PostToolUseFailure | PostToolUseFailure | Supported if a source is added |

Unclassified future events stay direct host registrations until their output and
failure semantics are reviewed.

Do not rely on `subagentStart` or `subagentStop` from Copilot's built-in
`general-purpose` agent. The 1.0.72-1 probe record conflicts with the docs, so
treat that row as unresolved and version-specific.

Keep script-side self-filtering as defense in depth. Matchers do work, but 1.0.57
and 1.0.58 shipped matcher bugs, so a hook that filters only through the host has
one point of failure.

### Adapter behavior

The PermissionRequest adapter accepts one complete JSON document regardless of
whitespace or pretty printing, and rejects trailing content after it. Translated
`approve` and `deny` require a string `reason`. Malformed exit-0 output is
diagnosed on stderr and suppressed so the host uses its documented default flow.
A translated `ask` emits nothing, because Copilot has no `ask` value.

The PostToolUse adapter captures plain stdout from successful observers,
preserves registration order, and emits one `{"additionalContext":"..."}` object
with a blank line between contributions. Failed-observer partial output is
discarded. It emits nothing when every observer is silent. It does not merge
`modifiedResult` or pre-structured JSON.

The Claude grouped dispatcher shares that process-level capture boundary and
emits one Claude protocol document. It treats only event-valid blocking shapes as
terminal: `continue: false`; Stop or SubagentStop `decision: block` with a string
reason; or nested PreToolUse `permissionDecision: deny` with a string reason.
Generic JSON with no protocol keys becomes context and later guards still run.
Malformed object-shaped JSON, allow-shaped decisions, unsupported decision
fields, and invalid field types fail closed in gate modes.

Discarding lifecycle prose means capturing Python streams, direct
file-descriptor writes, and inherited child-process output, then dropping the
content rather than turning repository text into model instructions.

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
python.exe: can't open file '...\project-toolkit/hooks/PreToolUse/_dispatch.py': [Errno 2] No such file or directory
```

POSIX reads `python3: can't open file` with forward slashes. Search for
`_dispatch.py` plus `Errno 2`, not the interpreter name, which varies by OS.

When `_direct` appears in that path, it identifies the local development shadow,
not the published install. Every tool call is denied for the rest of the
session, including read tools, because a `PreToolUse` launcher that cannot start
its interpreter fails closed before matcher evaluation.

Remedy: restart the Copilot session. Reinstalling the plugin without restarting
does not help when the root moved, since the exported value does not change.

Do not add an existence check to the launcher command strings. The interpreter
error already names the missing path, so a guard buys only the restart
sentence, and it costs branching logic inside the highest-blast-radius string in
the repository, in a generated artifact, in two shell dialects. This is the same
argument ADR-006 makes against logic in workflow YAML. Evidence: issues #3321
and #3332, GitHub Copilot CLI 1.0.72-1.

**SUPERSEDED for PreToolUse and PostToolUse launcher commands by issue #4672.**

The advice above remains correct for lifecycle events (SessionStart, etc.)
where a non-zero exit is informational, not blocking. For PreToolUse and
PostToolUse, the host interprets any non-zero exit as a policy denial and
surfaces it to the user as:

```text
Denied by preToolUse hook from "project-toolkit@ai-agents"
```

This means an infrastructure failure (missing file, missing interpreter, bad
root) that returns non-zero denies every tool call in every session. A plugin
that denies every tool call gets uninstalled, which removes 100% of protection.
Fail-open-with-warning keeps the plugin installed and the session working, so
the next release can still protect the user. Expected protection is strictly
higher with degrade-and-warn than with fail-closed-then-uninstall.

The following checks are now REQUIRED in PreToolUse/PostToolUse launcher
commands (both bash and powershell forms). Each must exit 0 with a warning to
stderr naming the plugin, the cause, and the remediation:

1. Plugin root unresolvable or not a directory
2. Python interpreter absent from PATH
3. Dispatcher script missing or unreadable
4. Python interpreter broken shim (shell exit 126 or 127)

The version check (Python below 3.10) lives inside _dispatch.py, not in the
shell command, to avoid a second subprocess per invocation.

The old concerns from #3321 and #3332 still hold for: (a) lifecycle events
where non-zero is not blocking, (b) any check that is not load-bearing for the
"never deny on infrastructure failure" contract. Do not add speculative guards
beyond the four above without a demonstrated denial scenario.

`test_stale_plugin_root_failure_names_the_missing_path` now asserts the
fail-open contract: stale root exits 0 with a warning naming the path.

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
