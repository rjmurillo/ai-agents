# Official Hook Contracts

Updated: 2026-08-13

This sidecar pins the official sources used by `agent-harness-reference`.
Future agents should refresh these sources, not repeat an open-ended search.

## Source priority

1. Current vendor reference pages.
2. Pinned vendor source commits for reproducibility.
3. Official CLI changelog for version transitions.
4. Versioned local probes for docs-silent or disputed runtime behavior.
5. DeepWiki only as a secondary repository index.

DeepWiki found changelog evidence in `github/copilot-cli`, but no public hook
runtime implementation for permission output, exit handling, timeout behavior,
or cloud execution. Do not cite DeepWiki as the authority for those rows.

DeepWiki cross-check:
<https://deepwiki.com/search/crosscheck-the-repository-for_89942bc1-641b-4aa2-bc9a-2f090ddd30fb>

## GitHub Copilot CLI

### Primary sources

- Current hook reference:
  <https://docs.github.com/en/copilot/reference/hooks-reference>
- Pinned hook reference source:
  <https://github.com/github/docs/blob/0b02cd6336f4eebda1e409b45a89dab5c2193d9a/content/copilot/reference/hooks-reference.md>
- Current cloud hook guide:
  <https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/use-hooks>
- Pinned cloud hook guide source:
  <https://github.com/github/docs/blob/3af7cb3042ac2f16645785e9f6dc89922d5e5588/content/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/use-hooks.md>
- Current plugin reference:
  <https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference>
- Current permission guide:
  <https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/allowing-tools>
- Current configuration guide:
  <https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/configure-copilot-cli>
- Pinned Copilot CLI changelog:
  <https://raw.githubusercontent.com/github/copilot-cli/fd24cea5cb11da4e630485ff2d9269318b8c2a4e/changelog.md>

### Configuration contract

| Question | Official answer | Source |
|---|---|---|
| Repository hook files | `.github/hooks/*.json` | Hook reference, Hooks locations |
| User hook files | `~/.copilot/hooks/*.json`, or `$COPILOT_HOME/hooks/*.json` | Hook reference, Hooks locations |
| Repository settings | `.github/copilot/settings.json`, `.github/copilot/settings.local.json`, `.claude/settings.json`, `.claude/settings.local.json` | Hook reference, Hooks locations |
| User settings | `~/.copilot/settings.json` | Hook reference, Hooks locations |
| Plugin hooks | plugin `hooks.json` or `hooks/hooks.json` | Hook reference, Hooks locations |
| Policy hooks | `/etc/github-copilot/policy.d/*.json`, Windows policy directory, or Windows Registry | Hook reference, Policy hooks |
| File wrapper | `{"version":1,"hooks":{...}}` | Hook reference, Hook configuration format |
| Command fields | `bash`, `powershell`, `command`, `cwd`, `env`, `timeout`, `timeoutSec`, optional `type` | Hook reference, Command hooks |
| Other hook types | HTTP hooks; sessionStart prompt hooks | Hook reference, HTTP hooks and Prompt hooks |

The hook reference says sources load in order "policy, then user, then project,
then plugins," but its bullet list places repository files before user files.
The docs conflict on exact precedence. All entries are combined and run. Do
not depend on cross-source precedence without a targeted probe.

The command-hook table defines `cwd` as relative to the repository root or
absolute. It does not promise the plugin directory as the working directory.
Anchor plugin files through a plugin-root variable.

### Permission controls

GitHub documents these Copilot CLI permission surfaces:

| Surface | Scope | Persisted |
|---|---|---|
| `--allow-tool`, `--deny-tool`, `--allow-all-tools` | Current CLI session | No |
| Interactive tool approval for the current location | User configuration, keyed by repository root or working directory | `permissions-config.json` under `COPILOT_HOME` |
| Trusted directories | User configuration | `config.json` under `COPILOT_HOME` |
| URL approvals | User configuration | `settings.json` under `COPILOT_HOME` |

The official permission and configuration guides document no repository-committed
file for fine-grained tool allow or deny rules. Status: DOCS SILENT on any
additional repo policy surface. Do not infer that a plugin can ship session flags
or user-global approvals. The 1.0.72-1 help inventory in `probe-evidence.md`
found no additional configuration key.

Sources: GitHub permission guide, Persisted permissions and Allowing or denying
permission for specific tools; configuration guide, Setting allowed tools.

### Exact native events

The official table lists 14 native events:

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

Source: hook reference, Hook events.

Documented compatibility aliases include:

- `agentStop` / `Stop`
- `errorOccurred` / `ErrorOccurred`
- `postToolUse` / `PostToolUse`
- `postToolUseFailure` / `PostToolUseFailure`
- `preCompact` / `PreCompact`
- `preToolUse` / `PreToolUse`
- `sessionEnd` / `SessionEnd`
- `sessionStart` / `SessionStart`
- `subagentStop` / `SubagentStop`
- `userPromptSubmitted` / `UserPromptSubmit`

PascalCase compatibility payloads use snake_case fields. Native camelCase
events use camelCase fields.

The built-in `general-purpose` agent does not emit subagentStart or
subagentStop. Other built-in YAML agents and custom agents do. Source: hook
reference, subagentStart.

### Matchers

Native matchers are optional regular expressions compiled as
`^(?:PATTERN)$`, so the full value must match. Invalid regular expressions skip
the hook entry.

Native matcher targets:

| Event | Target |
|---|---|
| notification | `notification_type` |
| permissionRequest | `toolName` |
| postToolUse | `toolName` |
| preCompact | `trigger` |
| preToolUse | `toolName` |
| subagentStart | `agentName` |

PascalCase PreToolUse and PermissionRequest use Claude-format matcher
semantics. Literals and `|` alternations match Claude tool names. Other
patterns are case-sensitive whole-name regular expressions.

Source: hook reference, Claude-format matchers and Matcher filtering.

Official changelog transitions:

- 1.0.44: fixed ignored `preToolUse.matcher`.
- Later release: PostToolUse matchers are honored.
- Later release: Claude-format PreToolUse and PermissionRequest tool matchers
  such as `Bash`, `Read`, and `*` fire correctly.

Source: pinned Copilot CLI changelog.

### PreToolUse output and failure

Documented top-level output:

```json
{
  "permissionDecision": "allow",
  "permissionDecisionReason": "Reason",
  "modifiedArgs": {}
}
```

`permissionDecision` accepts `allow`, `deny`, or `ask`.
`permissionDecisionReason` is required for deny.
`modifiedArgs` replaces the original tool arguments.

Command PreToolUse failures:

| Outcome | Contract |
|---|---|
| exit 0 with valid JSON | JSON controls the call |
| exit 2 | deny |
| other nonzero or crash | deny |
| timeout | fail open |
| malformed exit-0 JSON | ignored, default permission flow |
| empty exit-0 output | no hook decision |

HTTP PreToolUse network errors, non-2xx responses, and timeouts fail open.

Source: hook reference, PreToolUse decision control, fail behavior note, and
Exit codes for command hooks.

Top-level `decision: "deny"` is not the documented PreToolUse shape. The
`decision` field is documented for agentStop and subagentStop only.

### PermissionRequest output and failure

Documented output:

```json
{
  "behavior": "allow",
  "message": "Reason",
  "interrupt": false
}
```

`behavior` accepts only `allow` or `deny`. Empty output falls through to normal
permission handling. Exit 2 denies. The PermissionRequest section says stderr
is ignored on its exit-2 path.

`behavior: "ask"` is not valid. A translated Claude `ask` must emit nothing.

Source: hook reference, PermissionRequest decision control.

### Stop output

agentStop and subagentStop use:

```json
{
  "decision": "block",
  "reason": "Prompt for the next turn"
}
```

`block` forces another turn. Omitting `decision` permits completion. Current
Claude Code uses the same top-level `decision` and `reason` shape, so a shared
Stop producer needs no harness-specific adapter.

Sources: GitHub Copilot hook reference, agentStop / subagentStop decision
control; Claude Code hooks reference, Stop decision control.

The command-hook parser removes progress lines, concatenates all remaining
stdout, and performs one `JSON.parse`. Two final JSON objects concatenate into
invalid JSON and are ignored. A dispatcher must merge structured outputs into
one object or keep hooks as separate host registrations.

Source: hook reference, Progress messages.

### Other output fields

| Event | Documented output |
|---|---|
| PostToolUse | `modifiedResult`, `additionalContext` |
| Notification | `additionalContext` |
| UserPromptTransformed | `modifiedTransformedPrompt` |
| SessionStart | `additionalContext` |
| SubagentStart | `additionalContext` |
| PostToolUseFailure exit 2 | stdout is appended as `additionalContext` |
| PreCompact | DOCS SILENT: no config-file output field is documented |
| UserPromptSubmitted / UserPromptSubmit | DOCS SILENT: no config-file output field is documented. Probed 1.0.79-6: a top-level `additionalContext` is consumed, plain stdout is not |

`suppressOutput` is not present in the official config-file hook reference.
It appears in implementation-only SDK types. Status: DOCS SILENT for config
files. Do not use it in strict plugin hooks.

Repository consequence: the generated adapter emits `additionalContext` for
successful PostToolUse observers. It discards SessionStart and PreCompact stdout
because current producers include branch-controlled repository prose that must
not reach model-visible channels. Direct rollback commands suppress both stdout
and stderr while retaining producer side effects. It also discards
UserPromptSubmit stdout and stderr in dispatcher and direct rollback modes.
That choice tracks the documentation, which names no model-context field for
the event and leaves stderr reach silent. It does not track the runtime, which
is now measured: a direct `UserPromptSubmit` producer that needs model reach
emits the top-level `additionalContext` envelope itself, keyed on
`COPILOT_CLI`, rather than relying on plain stdout.
PostToolUseFailure remains a direct host registration so exit-2 stdout keeps its
documented recovery-context behavior. Unclassified events also remain direct
until reviewed. Partial output from failed consolidated observers is discarded
by repository policy, not by the host contract. Whether stderr enters model
context remains DOCS SILENT.

### Exit codes and stderr

| Exit | Official behavior |
|---|---|
| 0 | Parse stdout as hook output JSON |
| 2 | Warning and continue by default; deny for PreToolUse and PermissionRequest; PostToolUseFailure converts stdout to context |
| Other nonzero | Log and fail open, except PreToolUse denies |
| Timeout | Fail open for every event, including policy PreToolUse |

The general exit table says exit-2 stderr is surfaced to the user. The
PermissionRequest section says stderr is ignored for its exit-2 path.
Whether stderr enters model context is DOCS SILENT.

Source: hook reference, Exit codes for command hooks.

### Cloud agent

Cloud agent:

- loads only `.github/hooks/*.json`;
- requires the hook file on the default branch;
- runs in an ephemeral Linux sandbox;
- honors only `bash`, with `command` as fallback;
- pre-approves tools, so PermissionRequest is ineffective;
- does not fire notification;
- fires PreCompact only for automatic compaction;
- treats PreToolUse `ask` as deny;
- does not load user settings, repository settings, or installed plugins.

Sources: hook reference, Cloud agent execution environment and Hook events;
cloud hook guide, default-branch requirement.

### Plugin-root variables

The official Copilot CLI changelog states:

> Plugin hooks receive PLUGIN_ROOT, COPILOT_PLUGIN_ROOT, and
> CLAUDE_PLUGIN_ROOT env vars with the plugin's installation directory.

Source: pinned Copilot CLI changelog.

The hook reference does not list these variables in its cloud environment
table, which is expected because installed plugins do not run in cloud agent.

Note the scope: this entry covers **plugin** hooks and names three plugin-root
variables. It does not put `CLAUDE_PROJECT_DIR` on any Copilot surface, and no
vendor source does. See the environment inventory below.

### Environment variables Copilot CLI sets

| Variable | Contract | Status |
|---|---|---|
| `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT` | Plugin install directory, for plugin hooks | OFFICIAL, changelog quoted above |
| `COPILOT_CLI` | `1` in subprocesses Copilot spawns, so a subprocess can detect it is running under Copilot | OFFICIAL, changelog quoted below |
| `CLAUDE_PROJECT_DIR` | Not set. No vendor source places it on any Copilot surface | DOCS SILENT, and measured absent |

On `COPILOT_CLI`, the vendor changelog states, quoted verbatim:

> Git hooks can detect Copilot CLI subprocesses via the COPILOT_CLI=1
> environment variable to skip interactive prompts

Source: the `changelog.json` shipped inside the `@github/copilot` npm package,
under version key `0.0.421`, entry type `fixed`, referencing
`github/copilot-agent-runtime` pull request 4049. Read from the installed
package rather than a web copy, so the citation is the artifact the CLI ships
with.

Two consequences for a repository hook, both keyed on the fact that Copilot also
loads `.claude/settings.json` when the folder is trusted:

- An anchor of the form `cd "$CLAUDE_PROJECT_DIR"` expands to `cd ""` under
  Copilot, which sh and dash accept as a no-op, so a relative script path then
  resolves against the host's working directory. Anchor with a fallback.
- `COPILOT_CLI` identifies the process tree, not the consuming host. Copilot
  exports it into every shell it spawns, which is what the changelog entry
  describes, so a Claude Code session started from inside a Copilot shell
  inherits it. A hook choosing an output shape must check a positive Claude
  signal first.

Both are measured in `probe-evidence.md` section 8b, with positive controls.

## Claude Code

### Primary source

- Current hooks reference: <https://code.claude.com/docs/en/hooks>

The page is live vendor documentation. No pinned public source commit was
available in this research set. Refresh the live page when Claude Code changes.

### Exact documented event set

The official table lists 30 events:

```text
SessionStart
Setup
UserPromptSubmit
UserPromptExpansion
PreToolUse
PermissionRequest
PermissionDenied
PostToolUse
PostToolUseFailure
PostToolBatch
Notification
MessageDisplay
SubagentStart
SubagentStop
TaskCreated
TaskCompleted
Stop
StopFailure
TeammateIdle
InstructionsLoaded
ConfigChange
CwdChanged
FileChanged
WorktreeCreate
WorktreeRemove
PreCompact
PostCompact
Elicitation
ElicitationResult
SessionEnd
```

Source: Claude Code hooks reference, Hook lifecycle.

### PostToolUseFailure input

Claude Code sends a top-level `error` string and `is_interrupt` boolean in
addition to the common tool fields. The current reference says the error text
varies by tool and directs consumers to key on `tool_name`, `is_interrupt`, and
the `Exit code N` first line rather than treating the remaining display text as
a stable format.

Repository consequence: a failure observer reads `error` only after confirming
`hook_event_name == "PostToolUseFailure"`, and ignores interrupted calls. It
must not infer failure from words inside successful PostToolUse output.

Source: Claude Code hooks reference, PostToolUseFailure input.

### PostToolUseFailure output

Claude Code accepts an event-specific `additionalContext` string inside
`hookSpecificOutput`:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUseFailure",
    "additionalContext": "Additional information about the failure for Claude"
  }
}
```

Repository consequence: a failure observer emits this structured output and
returns exit 0. It does not use exit 2 or stderr for advisory context.

Source: Claude Code hooks reference, PostToolUseFailure decision control.

### PreToolUse deny

Claude Code documents:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Reason"
  }
}
```

Exit 2 blocks the tool call and sends stderr to Claude. This differs from
Copilot's top-level `permissionDecision` object.

Source: Claude Code hooks reference, How a hook resolves and Exit code 2
behavior.

### Stop output

Claude Code documents the same top-level Stop decision used by Copilot:

```json
{
  "decision": "block",
  "reason": "Must be provided when the harness is blocked from stopping"
}
```

Omitting `decision` allows Stop. Shared Stop producers can emit this shape on
both harnesses.

Source: Claude Code hooks reference, Stop decision control.

### Matcher contract

Claude matchers are event-specific. For tool events, a literal or `|`
alternation matches exact tool names. Patterns with other characters use an
unanchored JavaScript regular expression unless authors add `^` and `$`.
Current Claude Code also supports handler-level `if` conditions for command
arguments, such as `Bash(rm *)`.

Source: Claude Code hooks reference, Matcher patterns and How a hook resolves.

## Refresh procedure

1. Fetch the current primary page.
2. Compare it with the pinned source or the prior sidecar row.
3. Check the official CLI changelog for the version that introduced the delta.
4. Probe only runtime behavior that remains docs silent or contradicts docs.
5. Update this sidecar, `SKILL.md`, probe evidence, ADRs, tests, generated
   mirrors, and Serena memory in one change.
