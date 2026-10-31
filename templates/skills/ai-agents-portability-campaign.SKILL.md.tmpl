---
name: ai-agents-portability-campaign
description: Execute cross-harness hook changes for Claude Code and GitHub Copilot CLI using the settled official contract, versioned probes, generators, and runtime tests. Use for `run the portability campaign`, `port hooks to a new harness`, `copilot hook timeout regression`, or `new copilot cli release, recheck the contract`. Do NOT use for fact lookup alone (use `agent-harness-reference`) or release generation ownership (use `ai-agents-generation-and-release`).
version: 1.1.0
license: MIT
metadata:
  distribution: repo-local
  routing:
    role: front-door
    invoker: autoplan
    trigger: autoplan routes cross-harness hook port requests to ai-agents-portability-campaign
    user-facing: false
---

# ai-agents Portability Campaign

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths because its audience is repo contributors, not plugin consumers (issue #2050). Declared paths: .claude/lib/hook_dispatch.py, .project-toolkit/architecture/ADR-068-consolidated-hook-dispatcher.md, .project-toolkit/architecture/ADR-071-plugin-hook-runtime-contract-verification.md, .project-toolkit/architecture/ADR-097-zero-tool-use-hooks.md, build/scripts/generate_dispatcher.py, build/scripts/generate_hooks, scripts/hook_inventory.py, scripts/instruments.py, templates/platforms/copilot-cli.yaml -->

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
4. `.project-toolkit/architecture/ADR-068-consolidated-hook-dispatcher.md`
5. `.project-toolkit/architecture/ADR-071-plugin-hook-runtime-contract-verification.md`
6. `.project-toolkit/architecture/ADR-097-zero-tool-use-hooks.md`
7. `.claude/rules/generated-artifacts.md`

Do not run open-ended documentation research. Re-search or re-probe only when
the reference skill's refresh rules apply.

Current state (ADR-097, accepted): the `project-toolkit` plugin registers zero
PreToolUse, PostToolUse, and PostToolUseFailure hooks, and the generated Copilot
dispatcher is retired. `build/scripts/generate_dispatcher.py` and
`tests/build_scripts/test_generate_dispatcher.py` remain. Re-adding a tool-use
hook needs an ADR-097 re-evaluation and a rebuilt hardening-test bar. The
translation and merge rules in Phases 1 and 2 apply once a dispatcher exists.

Current load-bearing facts:

| Dimension | Settled contract |
|---|---|
| Event casing | PascalCase compatibility events deliver snake_case payloads |
| Stop | `Stop` is per-turn completion; `SessionEnd` is process lifecycle |
| PreCompact | Supported locally and in cloud automatic compaction |
| Matcher | Supported; PascalCase tool events use Claude-compatible tool names |
| PreToolUse deny | Top-level `permissionDecision`; nonzero denies; timeout fails open |
| PermissionRequest | `behavior` accepts only allow or deny; translated ask emits nothing |
| Observer output | A PostToolUse merger folds text into one `additionalContext`; SessionStart, PreCompact, and UserPromptSubmit adapters discard output; unclassified events stay direct. Applies only once a dispatcher exists again |
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

Read the Claude-to-Copilot event map from `eventRemap` in
`templates/platforms/copilot-cli.yaml`. Do not copy it here.

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-portability-campaign/scripts/instruments.py" --repo . run event-map
```

It prints the `eventRemap` block. It does not say which events have a
registration or what output form each takes. Use `hook_inventory.py counts`
(Phase 4) for registrations. Generated form per event, if a dispatcher is
rebuilt: PreToolUse and PostToolUse get a dispatcher with one source shim;
SessionStart, UserPromptSubmit, and PreCompact get an observe/discard adapter;
Stop, SubagentStop, SessionEnd, and PostToolUseFailure stay direct.

Why Stop stays direct: Copilot parses one final JSON document from each command
hook. Concatenating two decision objects makes invalid JSON and discards both.
The same parser boundary applies to `additionalContext`, `modifiedResult`, and
other structured outputs. A PostToolUse merger treats successful
observer stdout as ordered, flat context text and emits one `additionalContext`
object. Failed-observer partial output is discarded. It does not merge
`modifiedResult` or pre-structured JSON. SessionStart and PreCompact
adapters discard stdout and stderr. Their direct rollback tests preserve side
effects but suppress both channels. PostToolUseFailure stays direct because
exit-2 stdout becomes recovery
context. Copilot drops config-file UserPromptSubmit output, so its stdout is
redirected to stderr in dispatcher and direct rollback modes. Memory recall uses
the direct `userPromptTransformed` registration in
`.github/hooks/memory-recall.json` instead (issue #4727). Stderr is not a
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

Rules (dispatcher rules apply only if a dispatcher is rebuilt):

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

Count hook events and registrations per manifest:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-portability-campaign/scripts/hook_inventory.py" --repo . counts
```

It reads `.claude/settings.json`, `.claude/hooks/hooks.json`, and
`src/copilot-cli/hooks/hooks.json`. It does not judge whether a count is right.
Compare it with ADR-097: the two generated manifests stay at zero events until a
reviewed hook returns. Inactive generated event directories must be removed
through ownership-proven generation.

### Phase 5: Test Shipped Artifacts

```bash
uv run pytest \
  tests/build_scripts/test_hook_contract_knowledge.py \
  tests/e2e/test_cli_hook_e2e.py -q
```

Check that every pytest path this skill names exists:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-portability-campaign/scripts/hook_inventory.py" --repo . phase-tests
```

It checks existence in `.claude/skills/ai-agents-portability-campaign/SKILL.md`,
not whether the tests pass.

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
- [ ] Any new PreToolUse, PostToolUse, PermissionRequest, or PostToolUseFailure registration cleared the ADR-097 re-evaluation triggers.
- [ ] `hook_inventory.py qualifiers` exits 0 once every reference is qualified. Known red at 42e409325 (2026-10-31): src/AGENTS.md:34 lacks the qualifier.
- [ ] Targeted generator and runtime tests pass.
- [ ] Real CLI ran for runtime-only changes.
- [ ] Both project-toolkit plugin manifests are still version-free (`validate_plugin_version_bump.py` exits 0).
- [ ] No stale contract claim remains in requirements, audits, memories, or mirrors.

## Scripts

- `scripts/hook_inventory.py`: subcommands `counts`, `phase-tests`, `qualifiers` (Phases 4, 5, and Provenance).
- `scripts/instruments.py`: `list` shows every linked instrument and whether it exists; `run <id>` runs one.

Both are read-only. Exit codes: 0 ok, 1 findings, 2 bad arguments, 3 external failure.

## Provenance and Maintenance

Reconciled against ADR-097 and HEAD `42e409325` (2026-10-31). Facts and
checks live in `reverify.json`. Check the shipped references with:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-portability-campaign/scripts/hook_inventory.py" --repo . qualifiers
```

It lists every tracked file under `src/` and `.claude/skills/autoplan` that
names this skill and whether the line or paragraph says "ai-agents repository".
Exit 1 means an unqualified reference. It cannot judge whether the qualifier is
placed well.

Drift check:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/skill-bootstrap/scripts/bootstrap_drift.py" check --repo . --skills-root .claude/skills --name ai-agents-portability-campaign --require
```

Refresh this campaign after a host CLI version change, hook inventory change,
dispatcher design change, or vendor documentation update. First refresh
`agent-harness-reference` and its official and empirical sidecars. Then amend
affected ADRs, review them through `adr-review`, regenerate every mirror, and
rerun this skill's verification commands. Do not preserve dated inventory
counts as current operational guidance.
