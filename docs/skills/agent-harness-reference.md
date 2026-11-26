# agent-harness-reference

Gives you the recorded hook contract for Claude Code and GitHub Copilot CLI: events, matchers, payloads, decisions, exit codes, timeouts, and plugin roots. You get an answer with an official source or a versioned probe behind it, so you do not guess or search the web again.

## When to use it

- You are about to change a hook, dispatcher, generator, hook config, or runtime test.
- You need to know what a hook payload or decision looks like on either host.
- You hit a stale plugin root symptom, such as `Errno 2 _dispatch.py`.
- A self-improvement loop is about to edit its own prompts, skills, hooks, or agent files, and you need the editable and read-only surfaces.
- Trigger phrases: `harness contract`, `copilot cli hook behavior`, `hook payload format`, `cross-harness hook change`, `refresh hook evidence`, `stale plugin root`.

## When not to use it

- You want to run the porting campaign that changes hooks across hosts: use [`ai-agents-portability-campaign`](ai-agents-portability-campaign.md) instead. It works in a checkout of `rjmurillo/ai-agents`.
- You need to probe a missing or disputed contract row: use [`ai-agents-empirical-probe-toolkit`](ai-agents-empirical-probe-toolkit.md).
- You need to regenerate and release mirrors: use [`ai-agents-generation-and-release`](ai-agents-generation-and-release.md).

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:agent-harness-reference`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the agent-harness-reference skill to tell me what a Copilot CLI PreToolUse deny decision looks like and how it differs from Claude Code.
```

The agent reads the contract sidecar first, then answers with the field, its grade, and the source. It marks a field `DOCS SILENT` when the official docs say nothing, and it does not fill the gap from Claude behavior.

## What you get

- An answer graded by source: `OFFICIAL`, `EMPIRICAL` (a versioned runtime probe), or `CODE` (this repository's implementation).
- The `DOCS SILENT` label for rows the official docs do not answer.
- Repository decisions layered on the vendor contract, such as which hook events the repository registers and how adapters merge output.

Two facts the skill repeats because people guess them wrong:

| Topic | Claude Code | Copilot CLI |
| --- | --- | --- |
| PreToolUse deny JSON | `hookSpecificOutput.permissionDecision: "deny"` | top-level `permissionDecision: "deny"` |
| Exit 2 | Blocks and sends stderr to Claude | Denies PreToolUse and PermissionRequest only; other events continue |

On Copilot CLI, a timeout fails open on every event, including a policy PreToolUse gate.

## Advanced use

The skill orders its sources. When two disagree, the earlier one wins for authored behavior, and the conflicting probe stays on record as versioned evidence:

1. [`references/official-hook-contracts.md`](../../src/claude/skills/agent-harness-reference/references/official-hook-contracts.md): official sources, pinned commits, exact event sets, output fields, docs gaps.
2. The skill file itself: repository decisions derived from those contracts.
3. [`references/probe-evidence.md`](../../src/claude/skills/agent-harness-reference/references/probe-evidence.md): version-scoped runtime observations.
4. ADR-068 and ADR-071: dispatcher and runtime verification choices.
5. Serena memories: retrieval aids only. They never override the sources above.

Refresh the recorded contract only when one of these holds: the installed CLI version changed and the row depends on runtime behavior, an official URL no longer resolves, the sidecar marks the field `DOCS SILENT`, a real runtime result contradicts the record, or the field is missing from both the sidecar and the probe evidence. A refresh updates the sidecar, probe evidence, affected ADRs, runtime tests, generated mirrors, and memory in the same change.

The skill also records the stale plugin root failure. Copilot CLI resolves the plugin root once per process. If you delete or move the install directory mid-session, hooks fail until you restart the session. PreToolUse and PostToolUse launchers must exit 0 with a warning on infrastructure failure, so a broken launcher does not deny every tool call.

The verification checklist before a cross-harness hook change includes: classify each claim as official, empirical, or docs silent; keep `Stop` separate from `SessionEnd`; route PostToolUse text through one `additionalContext`; treat unknown Claude JSON as context, never as a terminal gate decision; and run the real target CLI when the change affects runtime-only behavior.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`ai-agents-portability-campaign`](ai-agents-portability-campaign.md): runs a contract change across hosts.
- [`ai-agents-empirical-probe-toolkit`](ai-agents-empirical-probe-toolkit.md): probes a missing or disputed row.
- [`ai-agents-generation-and-release`](ai-agents-generation-and-release.md): regenerates and releases mirrors.
- Source: [`SKILL.md`](../../src/claude/skills/agent-harness-reference/SKILL.md)
- Contract sidecar: [`official-hook-contracts.md`](../../src/claude/skills/agent-harness-reference/references/official-hook-contracts.md)
- Probe evidence: [`probe-evidence.md`](../../src/claude/skills/agent-harness-reference/references/probe-evidence.md)
- Harness optimization ladder, seven editable components, read-only boundary: [`harness-optimization.md`](../../src/claude/skills/agent-harness-reference/references/harness-optimization.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
