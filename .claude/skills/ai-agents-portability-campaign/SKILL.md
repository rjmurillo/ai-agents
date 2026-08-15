---
name: ai-agents-portability-campaign
description: Execute cross-harness hook changes for Claude Code and GitHub Copilot CLI using the settled official contract, versioned probes, generators, and runtime tests. Use for `run the portability campaign`, `port hooks to a new harness`, `copilot hook timeout regression`, or `new copilot cli release, recheck the contract`. Do NOT use for fact lookup alone (use `agent-harness-reference`) or release generation ownership (use `ai-agents-generation-and-release`).
version: 1.1.0
license: MIT
---

# ai-agents Portability Campaign

<!-- vendor-portability: repository-maintenance skill; source-tree paths name
canonical owners, not consumer-runtime dependencies. Issue #2050. -->

This skill changes hooks. `agent-harness-reference` owns hook facts.
`ai-agents-empirical-probe-toolkit` owns probe design.
`ai-agents-generation-and-release` owns mirror generation and the release path.

## Triggers

- `run the portability campaign`
- `port hooks to a new harness`
- `copilot hook timeout regression`
- `verify the copilot runtime contract`
- `new copilot cli release, recheck the contract`

## Process

### Phase 0: Load the Settled Contract

Read:

1. `.claude/skills/agent-harness-reference/SKILL.md`
2. `.claude/skills/agent-harness-reference/references/official-hook-contracts.md`
3. `.claude/skills/agent-harness-reference/references/probe-evidence.md`
4. `.agents/architecture/ADR-068-consolidated-hook-dispatcher.md`
5. `.agents/architecture/ADR-071-plugin-hook-runtime-contract-verification.md`
6. `.claude/rules/generated-artifacts.md`

Do not run open-ended documentation research. Re-search or re-probe only when
the reference skill's refresh rules apply.

Current load-bearing facts:

| Dimension | Settled contract |
|---|---|
| Event casing | PascalCase compatibility events deliver snake_case payloads |
| Stop | `Stop` is per-turn completion; `SessionEnd` is process lifecycle |
| PreCompact | Supported locally and in cloud automatic compaction |
| Matcher | Supported; PascalCase tool events use Claude-compatible tool names |
| PreToolUse deny | Top-level `permissionDecision`; nonzero denies; timeout fails open |
| PermissionRequest | `behavior` accepts only allow or deny; translated ask emits nothing |
| Observer output | Active PostToolUse text merges into one `additionalContext`; dormant SessionStart, PreCompact, and UserPromptSubmit adapters discard output; unclassified events stay direct |
| Cloud reach | Only default-branch `.github/hooks/*.json` loads |
| Plugin paths | Anchor through plugin-root variables; do not depend on cwd |

### Phase 1: Classify the Source Hook

For every source registration, record:

1. Claude event and Copilot event.
2. Input payload fields in each harness.
3. Matcher target and matcher syntax.
4. Output schema.
5. Exit, crash, timeout, and malformed-output behavior.
6. Local CLI and cloud reach.
7. Whether stdout is diagnostic text or documented structured host output.

Use this repository mapping:

| Claude source | Copilot target | Generated form |
|---|---|---|
| PreToolUse | PreToolUse | Active gate dispatcher, one source shim |
| PostToolUse | PostToolUse | Active observe dispatcher, one source shim, text to `additionalContext` |
| PermissionRequest | PermissionRequest | Supported translation path; no current producer |
| SessionStart | SessionStart | No current vendored source; observe/discard adapter if added |
| UserPromptSubmit | UserPromptSubmit | No current vendored source; observe/discard adapter if added |
| PreCompact | PreCompact | No current vendored source; observe/discard adapter if added |
| Stop | Stop | No current vendored source; separate direct registrations if added |
| SubagentStop | SubagentStop | Separate direct registrations if added |
| SessionEnd | SessionEnd | No current source registration; stays direct if added until reviewed |
| PostToolUseFailure | PostToolUseFailure | Direct registration preserves exit-2 recovery context |

Why Stop stays direct: Copilot parses one final JSON document from each command
hook. Concatenating two decision objects makes invalid JSON and discards both.
The same parser boundary applies to `additionalContext`, `modifiedResult`, and
other structured outputs. The active PostToolUse merger treats successful
observer stdout as ordered, flat context text and emits one `additionalContext`
object. Failed-observer partial output is discarded. It does not merge
`modifiedResult` or pre-structured JSON. Dormant SessionStart and PreCompact
adapters discard stdout and stderr. Their direct rollback tests preserve side
effects but suppress both channels. PostToolUseFailure stays direct because
exit-2 stdout becomes recovery
context. Copilot documents no output field for UserPromptSubmit, so its stdout is
redirected to stderr in dispatcher and direct rollback modes. Stderr is not a
documented model-context path. Every unclassified event stays direct until its
host contract is reviewed.

### Phase 2: Change Canonical Sources

Edit the smallest canonical surface:

- Hook script: `.claude/hooks/**`
- Hook registrations: `.claude/settings.json`
- Event mapping: `templates/platforms/copilot-cli.yaml`
- Copilot generation: `build/scripts/generate_hooks*.py` and
  `build/scripts/generate_dispatcher.py`
- Runtime adapter: `.claude/lib/hook_dispatch.py`

Do not hand-edit `src/copilot-cli/**`.

Rules:

- Keep PascalCase target events when source hooks expect snake_case payloads.
- Keep script-side matcher checks as defense in depth.
- Keep canonical Claude PermissionRequest output unchanged.
- Translate only in the generated Copilot dispatcher.
- Translate Claude `approve` to Copilot `allow`.
- Translate Claude `deny` to Copilot `deny`.
- Translate Claude `ask` to empty stdout.
- Never map Stop to SessionEnd.
- Never consolidate structured host output without a tested, event-specific
  merger.
- Merge PostToolUse context text into one `additionalContext`.
- Capture SessionStart and PreCompact Python stdout and stderr, direct writes
  to file descriptors 1 and 2, and inherited child-process output on both
  channels. Discard the content unless a reviewed trust boundary makes it safe
  model context.
- Reuse the same process-level capture in Claude grouped dispatch. Python-only
  stream capture does not protect the single-document protocol.
- Treat unknown Claude JSON as context and continue later gates.
- Treat only event-valid Claude blocking shapes as terminal: `continue: false`;
  Stop or SubagentStop `decision: block` with a string reason; or nested
  PreToolUse `permissionDecision: deny` with a string reason. Fail closed on
  malformed object-shaped JSON, allow-shaped decisions, unsupported fields, and
  invalid field types.
- Reject empty, malformed, event/mode-mismatched, duplicate, or path-escaping
  Claude dispatch groups before any shim runs.
- Keep direct rollback commands for SessionStart and PreCompact silent on both
  stdout and stderr while preserving producer side effects.
- Keep PostToolUseFailure direct unless an event-specific merger preserves
  exit-2 recovery context.
- Discard UserPromptSubmit stdout and stderr. Do not invent fields or treat
  undocumented stderr as model context.
- Keep unclassified events direct. Do not assign observe mode by default.

### Phase 3: Test Before Generation

Run the smallest suites that cover the changed contract:

```bash
uv run pytest \
  tests/build_scripts/test_generate_dispatcher.py \
  tests/build_scripts/test_generate_hooks.py \
  tests/test_hook_dispatch.py -q
```

For a launcher or cwd change, also run:

```bash
uv run pytest \
  tests/build_scripts/test_generate_hooks_runtime_contract.py \
  tests/build_scripts/test_generate_hooks_plugin_root.py -q
```

Every runtime-contract test needs a negative control. A test that compares the
generator with its own expected string is one closed loop.

### Phase 4: Regenerate All Mirrors

Use `ai-agents-generation-and-release`. The required outcome is one coherent
change containing canonical sources and every generated artifact.

```bash
uv run python build/scripts/build_all.py
```

Current inventories:

- Local `.claude/settings.json`: six events, seven registrations.
- Vendored `.claude/hooks/hooks.json`: two events, four registrations.
- Generated `src/copilot-cli/hooks/hooks.json`: two events, two dispatcher
  registrations.

Expected generated Copilot hook shape:

| Event | Entries |
|---|---:|
| PostToolUse | 1 dispatcher |
| PreToolUse | 1 dispatcher |

No `PermissionRequest` policy hook is registered. Generic `advise` translation
remains covered by generator and dispatcher tests for a future reviewed policy.

Only the generated PreToolUse and PostToolUse event directories may remain.
Inactive event directories must be removed through ownership-proven generation.

### Phase 5: Test Shipped Artifacts

```bash
uv run pytest \
  tests/build_scripts/test_copilot_dispatcher_artifact.py \
  tests/build_scripts/test_hook_contract_knowledge.py \
  tests/e2e/test_cli_hook_e2e.py -q
```

Run the isolated real-CLI smoke when hook paths, event names, matchers,
decisions, exit handling, or timeout behavior changed:

```bash
uv run pytest tests/e2e/test_plugin_load_smoke.py -q
```

The smoke uses `--plugin-dir`; it must not install or mutate the user's default
plugin.

### Phase 6: Refresh Knowledge Only When Needed

If the runtime matches the settled contract, do not create a new research
artifact.

If the runtime differs:

1. Pin the CLI version.
2. State the expected result before probing.
3. Use an isolated plugin and foreign cwd.
4. Capture raw stdin, cwd, env, stdout, stderr, and exit.
5. Run a negative control.
6. Compare the previous pinned version when possible.
7. Update the official sidecar, probe evidence, affected ADRs, tests, generated
   mirrors, and Serena memory together.

Do not replace an official statement with a single probe. Record the conflict
and scope the observation to the measured version.

## Anti-Patterns

| Wrong path | Why it fails |
|---|---|
| Map `Stop` to `SessionEnd` | Converts per-turn validation into process cleanup |
| Copilot nested `hookSpecificOutput.permissionDecision` | Copilot PreToolUse expects top-level fields |
| Copilot top-level `decision: "deny"` for PreToolUse | `decision` belongs to Stop events |
| Copilot PermissionRequest `behavior: "ask"` | Official schema permits only allow or deny |
| JSON-only denial with exit 0 after a hook crash | PreToolUse nonzero is the documented fail-closed path |
| Raising timeout to obtain fail-closed behavior | Copilot timeouts always fail open |
| One observe dispatcher for multiple Stop decisions | Concatenates JSON and loses every decision |
| Assuming matchers are ignored | Current docs and 1.0.72-1 prove selective firing |
| Depending on general-purpose subagent events | Current docs say that agent emits neither event |
| Hand-editing `src/copilot-cli/**` | Regeneration overwrites it and drift gates fail |
| Repeating settled web research | Wastes tokens and risks replacing pinned facts with weaker sources |

## Extension Points

When a harness adds an event or output field, update
`agent-harness-reference` first. Then extend this campaign's mapping, generator
tests, shipped-artifact tests, real CLI probe, and generated mirrors together.

## Verification

- [ ] Official sidecar and probe evidence were read.
- [ ] Each hook has an event, payload, matcher, output, failure, and cloud classification.
- [ ] PermissionRequest ask produces empty stdout.
- [ ] No multi-producer structured output is concatenated.
- [ ] PreCompact remains available in `eventRemap`, even with no active vendored registration.
- [ ] Canonical and generated artifacts changed together.
- [ ] Targeted generator and runtime tests pass.
- [ ] Real CLI ran for runtime-only changes.
- [ ] Both project-toolkit plugin manifests are still version-free (`validate_plugin_version_bump.py` exits 0).
- [ ] No stale contract claim remains in requirements, audits, memories, or mirrors.

## Provenance and Maintenance

Verified 2026-08-14 against `.claude/settings.json`,
`.claude/hooks/hooks.json`, generated Copilot manifests, ADR-068, ADR-071,
ADR-085, `agent-harness-reference`, and the hook contract knowledge tests.

Refresh this campaign after a host CLI version change, hook inventory change,
dispatcher design change, or vendor documentation update. First refresh
`agent-harness-reference` and its official and empirical sidecars. Then amend
affected ADRs, review them through `adr-review`, regenerate every mirror, and
rerun this skill's verification commands. Do not preserve dated inventory
counts as current operational guidance.
