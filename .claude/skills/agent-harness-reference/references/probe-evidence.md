<!-- vendor-portability: contributor-facing knowledge pack for this repository; paths name canonical sources intentionally -->

# Probe Evidence Behind the Hook Contract

Updated: 2026-07-22

This file records version-scoped runtime observations. Official behavior belongs
in `official-hook-contracts.md`. Keep a probe here when the docs are silent, when
runtime behavior contradicted the docs, or when a negative control proves a
repository decision is load-bearing.

## 1. Plugin root and cwd

Issue #2205, session 1873.

Versions:

- GitHub Copilot CLI 1.0.57
- Claude Code 2.1.159

Method:

1. Install a probe plugin.
2. Run its hook from a directory outside the plugin tree.
3. Record the hook cwd and the three plugin-root variables.
4. Execute the generated anchored launcher.
5. Execute a bare `./hooks/...` negative control.

Observed:

- Copilot ran the plugin hook from the configured user working directory.
- `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT`, and `CLAUDE_PLUGIN_ROOT` pointed to the
  plugin installation directory.
- The plugin-root anchored launcher found and executed its script.
- The bare relative launcher did not find its script.
- Claude Code exported `CLAUDE_PLUGIN_ROOT` for its installed plugin.

The official Copilot CLI changelog now documents all three Copilot plugin-root
variables. The probe remains evidence for their 1.0.57 values and for the
foreign-cwd negative control.

Durable test:
`tests/build_scripts/test_generate_hooks_runtime_contract.py`.

## 2. Payload casing

Issue #2290, Copilot CLI 1.0.58.

Method:

1. Register the same tool event with native camelCase and PascalCase keys.
2. Capture stdin from each registration.
3. Compare field names and argument types.

Observed:

```text
camelCase event: toolName and toolArgs
PascalCase event: tool_name and tool_input
```

`toolArgs` was a JSON string in the native payload. `tool_input` was already an
object in the PascalCase payload. This is why the repository keeps PascalCase
compatibility registrations for Claude-authored hook scripts.

The earlier plugin-root probe captured environment only. It did not establish
payload casing. Tests that constructed their own payload could not prove the
host shape.

## 3. Historical timeout and kill evidence

Issue #2295, Copilot CLI 1.0.57 era.

Observed on Windows:

```text
Python hook cold start: about 246 ms
Sequential aggregate: about 8.7 seconds
Observed host kill: about 2 to 3 seconds
```

Three of 197 PreToolUse invocations were killed. Exit 143 indicated SIGTERM,
not a payload parse failure. This evidence motivated dispatcher consolidation.
It does not describe current timeout policy.

Copilot CLI 1.0.72-1 failed open in the timeout probe below.

## 4. Copilot CLI 1.0.72-1 contract correction

Date: 2026-07-19.

Method:

- isolated `--plugin-dir` probes;
- no mutation of the user's installed plugin;
- selective event and matcher registrations;
- decision-shape positive and negative controls;
- timeout and exit-code controls.

Observed event and matcher behavior:

```text
PascalCase PreToolUse matcher Bash fired for Bash.
The same hook did not fire for Edit.
Stop and native agentStop fired on continued prompt legs.
SessionEnd fired separately with reason=complete.
PascalCase SubagentStop fired after a child selected as general-purpose.
```

Current docs say the built-in `general-purpose` agent emits no subagentStart or
subagentStop event. The SubagentStop row remains a version-specific discrepancy.
Do not rely on general-purpose subagent events.

Observed PermissionRequest behavior:

```text
Claude {"decision":"approve","reason":"R"} was ignored.
Copilot {"behavior":"allow","message":"R","interrupt":false} approved.
Empty exit-0 output used normal permission handling.
```

Normal permission handling denied in the noninteractive probe. That denial was
the surrounding mode, not a hook-level meaning for empty output.

Observed failure behavior:

```text
PreToolUse exit 2 denied and skipped the tool.
timeoutSec 2 timed out, then the tool executed.
```

PreCompact registration succeeded, but the first probe did not trigger
compaction. A second Copilot CLI 1.0.72-1 probe used an authenticated isolated
home, a valid ai-agents repository identity, and the generated plugin. The
interactive `/compact` command reported `Compaction completed` but wrote no
PreCompact checkpoint. Invoking the generated PreCompact dispatcher directly
under the same plugin and project-root contract exited 0 and wrote one
checkpoint. Manual `/compact` is therefore a negative control, not a
PreCompact trigger. Automatic-compaction delivery remains unmeasured. Official
docs establish the event and its local and cloud trigger limits.

## 5. Copilot CLI 1.0.72-1 permission-surface inventory

Date: 2026-07-20.

Method:

1. Set isolated `HOME` and `COPILOT_HOME` directories.
2. Run `copilot --version`.
3. Run `copilot help permissions`.
4. Run `copilot help config`.
5. Search top-level help for permission and configuration options.

Observed:

```text
GitHub Copilot CLI 1.0.72
Tool permission flags: --allow-tool, --deny-tool, --allow-all-tools
Tool availability flags: --available-tools, --excluded-tools
Config help listed no fine-grained tool allow or deny setting
```

The help inventory agrees with the official docs: command flags are session
inputs, while saved approvals live under the user's `COPILOT_HOME`. Neither
source documents a repository-committed permission file that a plugin can ship.
This is a bounded inventory, not proof that no undocumented internal mechanism
exists.

Negative control: `copilot help config` enumerated persisted config keys,
including URL and trusted-directory settings, but no tool-command allow or deny
key. The official guide identifies `permissions-config.json` as an automatically
managed user file, not a repository artifact.

## 6. Pinned-package runtime verification and Copilot auto-update

Date: 2026-07-22.

Versions:

- `@github/copilot@1.0.73`
- `@anthropic-ai/claude-code@2.1.217`

Method:

1. Install both exact npm package versions into isolated prefixes with API,
   GitHub, and npm credentials removed from the installation environment.
2. Run each binary from the isolated prefix.
3. Repeat Copilot from a fresh prefix with `--no-auto-update`.
4. Run the committed real-CLI hook and plugin-load smokes against the pinned
   binaries.

Observed:

```text
copilot --version after exact package install: GitHub Copilot CLI 1.0.74-0
copilot --no-auto-update --version from a fresh install: GitHub Copilot CLI 1.0.73
claude --version: 2.1.217 (Claude Code)
pinned Copilot smoke: 3 passed
pinned Claude smoke: 2 passed
```

An exact `@github/copilot` npm package pin does not pin the executed binary by
itself. Copilot can update at process startup. Every committed Copilot smoke
command therefore goes through `copilot_command`, which inserts
`--no-auto-update` before the command arguments. The nightly workflow's package
pin and the helper's runtime flag are one contract; removing either makes the
recorded version ambiguous.

Durable tests:

- `tests/e2e/copilot_hook_probe.py`
- `tests/e2e/test_plugin_load_smoke.py::test_copilot_commands_disable_auto_update`
- `tests/test_nightly_cli_smoke_security.py`

## 7. Skill-description context cost and `disable-model-invocation`

Issue #4381, session 3605, 2026-07-27. Full write-up in Serena memory
`decision-skill-description-context-cost`; this is the cross-harness record,
because a Serena memory is MCP-gated and does not bind Copilot or Codex.

Version: Claude Code 2.1.220, model `claude-fable-5`.

Method: `claude -p "hi" --allowed-tools "" --output-format json`, summing
`input_tokens + cache_creation_input_tokens + cache_read_input_tokens`, against
a clean profile isolated with `CLAUDE_CONFIG_DIR`, with synthetic project
skills carrying unique 1,000-character descriptions.

Observed, tokens over a zero-skill baseline of 21,129:

| project skills | tokens | delta |
|---|---|---|
| 0 | 21,129 | 0 |
| 25 | 38,222 | +17,093 |
| 50 | 38,391 | +17,262 |
| 100 | 38,670 | +17,541 |
| 200 | 37,941 | +16,812 |
| 50, all `disable-model-invocation: true` | 21,525 | +396 |

Three results follow. Description cost is real but **saturates** near +17,000
tokens at roughly 24 skills, so it does not scale with the skill count.
`disable-model-invocation: true` collapses it to about 8 tokens per skill, the
name and its separator. Listing order is alphabetical by skill name, verified by
a permutation fixture whose alphabetical order was the reverse of its creation
order.

Two negative controls matter more than the table. Running the same experiment
against the author's real profile, which carried 264 global skills, produced a
376-token spread across 0 to 200 project skills and would have concluded
descriptions are never loaded; isolate the profile or the measurement is
worthless. And a fixture whose descriptions repeated one sentence tokenized far
cheaper than its character count, halving the apparent ceiling; use dense,
distinct text.

One consequence is **refuted**, which is why no rollout followed. A skill 51st
alphabetically, past the saturation ceiling, auto-invoked correctly on a unique
trigger phrase on the first try across three runs, with a single `Skill` tool
call and no preceding `Grep`, `Glob`, or `Read`. So "past the ceiling means not
auto-invocable" is false, the saturation mechanism is unsettled, and the
strongest argument for converting skills does not hold.

Copilot CLI 1.0.78-3 was probed separately with an isolated project containing
two valid skills and one negative control:

- `probe-default` had ordinary frontmatter.
- `probe-disabled` added `disable-model-invocation: true`.
- `probe-invalid` carried a 1,025-character description.

Command: `copilot -C <fixture> skill list --json`.

Both valid skills appeared with their full, unique descriptions and
`enabled: true`. The disabled fixture therefore had no observable inventory
effect. The negative control did not load, and stderr reported `Skill
description must be at most 1024 characters`, proving the command parsed and
validated supported frontmatter rather than accepting every field blindly.
This probe establishes inventory behavior only. It does not establish
prompt-token cost or auto-invocation behavior.

Authoring consequence, which is the decision this evidence supports: set
`disable-model-invocation: true` when Claude Code should require direct human
invocation, and judge that on invocation semantics, not on context accounting.
Do not set it to save tokens. The saving saturates, and Claude Code removes
automatic invocation by design. Copilot CLI 1.0.78-3 showed no inventory
effect, so this evidence does not support a claim that the same frontmatter
creates user-only behavior there.

Re-measure before relying on the numbers: server-side prompt changes can move
them without a CLI version bump.

## 8. Re-running a probe

Use `ai-agents-empirical-probe-toolkit` recipe 1.

Minimum evidence:

1. Record `copilot --version` or `claude --version`.
2. Run from a cwd outside the plugin root.
3. Capture environment and stdin.
4. Include a deliberately wrong negative control.
5. Separate official claims from observations.
6. Record interactive or noninteractive permission mode.
7. Update the official sidecar only for vendor statements.
8. Update this file, the contract skill, ADRs, tests, mirrors, and Serena memory
   in the same change.
