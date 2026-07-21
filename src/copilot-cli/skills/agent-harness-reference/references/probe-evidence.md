<!-- vendor-portability: contributor-facing knowledge pack for this repository; paths name canonical sources intentionally -->

# Probe Evidence Behind the Hook Contract

Updated: 2026-07-20

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

## 6. Re-running a probe

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
