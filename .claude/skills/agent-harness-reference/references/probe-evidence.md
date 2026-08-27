<!-- vendor-portability: contributor-facing knowledge pack for this repository; paths name canonical sources intentionally -->

# Probe Evidence Behind the Hook Contract

Updated: 2026-08-08

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

## 7. Python command permission and script identity

Issue #4764, 2026-08-08. RETIRED as live wiring: issue #5154 deleted the
identity guard from both harnesses on 2026-08-18 (ADR-085 Decision 8). The
harness-contract findings below stay because they describe the permission
surface, which is unchanged. The guard they were gathered for is gone.

Versions:

- GitHub Copilot CLI 1.0.79-6
- Claude Code 2.1.223

Method:

1. Create a repository-controlled `attacker/pr/new_pr.py`.
2. Run it under the `/push-pr` Python permission matcher.
3. Repeat with an installed plugin and its PreToolUse identity gate.
4. Run the installed plugin's real `new_pr.py --help` as the positive control.
5. Restrict the Copilot probe to Bash, so another execution tool cannot hide
   the Bash hook result.

Observed:

```text
Claude Bash(python3:*/pr/new_pr.py*) did not grant either command.
Claude Bash(python3 */pr/new_pr.py*) granted the lookalike command.
Claude PreToolUse matcher Bash(python3 */pr/new_pr.py*) did not fire.
Claude PreToolUse matcher Bash fired and denied the lookalike with exit 2.
Copilot PreToolUse matcher Bash denied the lookalike with exit 2.
Both hosts allowed the runtime plugin through python3 -I new_pr.py --help.
```

Claude hook `matcher` filters the tool name, not the Bash command. Current
Claude documentation provides the handler-level `if` field for command input
matching. The shared Claude and Copilot registration uses the bare `Bash`
matcher instead, then checks the command inside the Python guard. This keeps one
enforcement path across both generated surfaces.

The guard anchors trust to the plugin tree containing the running guard. It does
not trust a repository copy at the expected relative path, an environment
variable alone, a suffix match, a shell glob, or a symlink. It resolves the
plugin-root expression the same way as the shell, then compares that result to
the runtime plugin tree. The required Python `-I` flag blocks repository
`PYTHONPATH` and user-site import injection.

Copilot can execute Python through an unrelated MCP tool when that tool has
separate session approval. A Bash hook cannot intercept another tool's call.
Issue #4763 owns that broader per-skill permission boundary. Issue #4764 removes
the automatic Python grant and adds a Bash identity gate. It does not claim a
plugin can govern every execution tool.

Durable tests:

- `tests/hooks/test_dispatch_groups_parity.py`

The guard's own test files went with it in #5154. The name recorded here
before that, `tests/hooks/test_push_pr_script_identity_guard.py`, had already
been split into per-area files and did not exist under that name.

### 7a. Relevance before policy on the plugin-wide Bash matcher

Issue #4825, Copilot review 4894113215, 2026-08-10.

The bare `Bash` matcher above means the guard runs on every Bash command. The
first implementation applied its deny policy before deciding whether the
command was related to `new_pr.py`, so installing the plugin denied ordinary
work.

Method: drive the committed guard script directly with the host payload shape
(`{"tool_input": {"command": ...}, "cwd": ...}`), 22 commands unrelated to
`new_pr.py` and 11 `new_pr.py` attempts, and record the exit code of each.

Observed, before the relevance gate:

```text
irrelevant commands denied: 15 of 22
new_pr.py attempts denied:  11 of 11
denied: git status && git diff, bash -c, sh -c, node -e, perl -e,
        python3 <other>.py, uv run pytest, rg --files | head, git fetch,
        make build, npm run lint, eval, env LD_PRELOAD=... ls, echo *.py,
        uv run python -c
```

Observed, after the relevance gate:

```text
irrelevant commands denied: 0 of 22
new_pr.py attempts denied:  11 of 11
```

The negative control is the second row: a scope gate that let a `new_pr.py`
attempt through would show a nonzero "allowed" count there. Both surfaces are
covered by `test_dispatchers_allow_commands_outside_guard_scope` and
`test_dispatchers_deny_commands_inside_guard_scope`.

Accepted residual: a command that reconstructs the path at runtime without
naming it (`python3 -c` with a hex-decoded path, `ext::sh -c` with a payload
that never spells `new_pr.py`) is outside the detection surface. The guard
bounds the identity of named push-pr invocations; it is not a Python or shell
sandbox. `test_dispatchers_allow_dynamic_launcher_that_never_names_the_script`
pins that boundary so it stays a decision rather than a discovery.

## 8. UserPromptSubmit output shape on the repository settings surface

Issue #4727.

Version: GitHub Copilot CLI 1.0.79-6, Linux. Isolated `COPILOT_HOME`, folder
trust granted, `--no-custom-instructions` so no plugin or instruction layer
could inject the sentinel.

Method: register a `UserPromptSubmit` command hook, submit one prompt, and ask
the model whether it saw an opaque sentinel absent from the prompt text. Vary
only the output form.

Observed:

| Surface | Event | Payload | Ran | Reached model |
|---|---|---|---|---|
| `.github/hooks` | `UserPromptSubmit` | `{"additionalContext":"..."}` | yes | yes |
| `.github/hooks` | `userPromptSubmitted` | `{"additionalContext":"..."}` | yes | yes |
| `.github/hooks` | `UserPromptSubmit` | plain text | yes | no |
| `.claude/settings.json` | `UserPromptSubmit` | plain text | yes | no |
| `.claude/settings.json` | `UserPromptSubmit` | `{"additionalContext":"..."}` | yes | yes |

The negative control is the matched pair on the last two rows: same file, same
event, same session shape, differing only in output form. Plain stdout was
discarded and the envelope arrived, so the discarded payload cannot be blamed
on the hook failing to run.

Repository hooks do load from `.claude/settings.json` when the folder is
trusted; the runtime log line is `Loading repo hooks in prompt mode (folder is
trusted or opt-in set)`. An earlier probe showing nothing firing was an
untrusted-folder artifact.

Docs remain silent on an output field for this event, so this is
version-scoped empirical behavior, not a vendor guarantee.

### 8b. Which environment variables identify the host

The rows above establish the output shape. They say nothing about how a hook
decides which host is reading it, and an earlier version of this section
asserted that `CLAUDE_PROJECT_DIR` "is set under both hosts" with no probe row
and no citation. That claim was wrong. What follows replaces it.

Version: GitHub Copilot CLI 1.0.80 (`copilot --version`), Linux, installed from
`@github/copilot` for this measurement. Note the version differs from the
1.0.79-6 used for the output-shape rows above; these are separate measurements.

Method: byte search of the two shipped implementation artifacts,
`node_modules/@github/copilot-linux-x64/app.js` (9,173,451 bytes) and the
`copilot` engine binary (177,343,296 bytes). A live session probe was not
possible in this environment: `copilot -p` refused with "Authentication token
found but could not be validated", because the sandbox's GitHub proxy binds
sessions to configured repositories and blocks the user-login endpoint the CLI
calls at startup. So this is a static measurement of the shipped implementation,
not an observation of a running hook subprocess. It is graded accordingly.

Observed occurrences:

| String | `app.js` | `copilot` binary | Role |
|---|---|---|---|
| `COPILOT_CLI` | 12 | 3 | positive control |
| `additionalContext` | 24 | 0 | positive control |
| `GITHUB_TOKEN` | 27 | 0 | positive control |
| `COPILOT_PLUGIN_ROOT` | 1 | 0 | positive control |
| `CLAUDE_PROJECT_DIR` | 0 | 0 | the question |
| `CLAUDE_CODE_ENTRYPOINT` | 0 | 0 | the question |

The four positive controls are the negative control for the search itself: a
method that finds `additionalContext` 24 times in the same file on the same pass
is not failing to find `CLAUDE_PROJECT_DIR`. Read the two zero rows as exactly
what they say: this build never names the string, so Copilot CLI is not itself
the setter. That is strictly weaker than "a hook subprocess never receives the
variable", and no static search can close the gap. A child inherits every
variable its parent exported whether or not its own source spells the name, the
same inheritance this section relies on below for nested sessions. An earlier
revision of this paragraph drew the stronger conclusion,
reasoning that a variable the implementation never spells cannot be set by it.
That inference is invalid for environment variables and is withdrawn. Only a
read of a running hook subprocess's own environment settles what a hook
receives; issue #5369 tracks that live probe.

That gap is not hypothetical: a live read already exists and disagrees. The
"Harness detection" section of issue #4727 lists the environment visible to a
repo hook under Copilot CLI 1.0.79-6, includes `CLAUDE_PROJECT_DIR`, and states
it "is set under Copilot and cannot distinguish harnesses". A live read
outranks a static search on what a hook receives, so the row above must not be
restated as "Copilot does not export `CLAUDE_PROJECT_DIR`". The two results are
compatible in ways this evidence cannot separate: inheritance from the
launching shell, a name the artifact never spells literally, or a difference
between 1.0.79-6 and 1.0.80. Treat presence as CONTESTED and anchor defensively
regardless; the `:-` fallback is correct whether the variable is set, unset, or
inherited, so the fix never depended on settling this.

Caveat recorded rather than hidden: every `COPILOT_CLI` hit in this table is a
`COPILOT_CLI_*`-prefixed name (`COPILOT_CLI_VERSION`, `COPILOT_CLI_DIST_DIR`,
`COPILOT_CLI_ENABLED_FEATURE_FLAGS`). The bare `COPILOT_CLI=1` variable is not
visible as a standalone literal in either artifact.

**Correction, dated 2026-08-27 (issue #5369).** This section previously said the bare
variable's "authority here is the vendor changelog quoted in
official-hook-contracts.md, not this search." That changelog citation has
since been re-verified against the actual installed `@github/copilot` package
(every published version, via `npm pack`) and does not exist: no such entry,
no such quoted text, no reference to the cited pull request, in any
`changelog.json`. A follow-up byte search of the shipped
`@github/copilot-linux-x64@1.0.80` `app.js` for a bare `COPILOT_CLI` literal
(distinct from the `COPILOT_CLI_*`-prefixed names above) finds exactly one
occurrence: `Fe.COPILOT_CLI="copilot_cli"`, an internal feature-flighting enum
key, not an environment variable read or write. Official GitHub Copilot CLI
docs and a community environment-variable reference for the CLI do not list a
bare `COPILOT_CLI` variable either. There is currently no vendor-confirmed
source for `COPILOT_CLI` as a host-identifying environment variable. See the
"Environment variables Copilot CLI sets" correction in
`official-hook-contracts.md` for the full account.

Consequence for the anchor. Every command in `.claude/settings.json` opened with
`cd "$CLAUDE_PROJECT_DIR"`, and Copilot loads that same file when the folder is
trusted. With the variable unset, `cd ""` is a silent no-op: exit 0, cwd
unchanged, nothing on stderr. Re-measured 2026-08-27 in dash (this platform's
`/bin/sh`) and bash, since POSIX leaves an empty operand unspecified and the
claim is per-shell rather than universal: `sh -c 'cd "" && echo ran'` prints
`ran` and exits 0, so the chain continues and the anchor fails to move rather
than failing. Measured from a repository subdirectory with the variable
removed, running the registered recall command two ways:

| Anchor | cwd after `cd` | Exit | stdout |
|---|---|---|---|
| `cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"` | repository root | 0 | `<memory-context>` block |
| `cd "$CLAUDE_PROJECT_DIR"` (control) | the subdirectory | 2 | empty; `can't open file ... [Errno 2]` |

Read the control's exit 2 carefully: it is not `cd` failing. `cd ""` returned 0
and the chain ran on; Python then could not open the relative script path from
the unchanged cwd, which the recorded `[Errno 2]` names. A launcher that failed
at `cd` would stop before running anything, while this one walks into the wrong
directory, which is what makes the bare anchor dangerous rather than broken.

Exit 2 on `UserPromptSubmit` blocks prompt processing and erases the user's
prompt (issue #4011), so the bare anchor was worse than inert on this event. The
settings file now carries the `:-` fallback, and
`test_every_launcher_resolves_with_the_project_dir_unset` in
`tests/test_memory_hook_registration.py` runs every registered launcher this way
with the bare form as an in-test negative control.

Consequence for the output shape: the memory-recall `UserPromptSubmit` hook
emits the top-level envelope when `COPILOT_CLI` is set and no Claude signal is,
and keeps plain stdout otherwise. This is a best-effort heuristic, not a
verified contract: per the correction above, `COPILOT_CLI` is not confirmed to
be set by Copilot CLI at all, so whether this branch ever fires under real
Copilot CLI is open. `CLAUDE_CODE_ENTRYPOINT` is the only confirmed signal and
takes precedence regardless (it is absent from this Copilot build per the
table above, and observed set to `remote_mobile` in a Claude Code session on
the same machine), both because it fails safe for Claude and because, if
`COPILOT_CLI` does turn out to be real, it would not identify the consuming
host by itself: Copilot would export it into every shell it spawns, so a
Claude session started underneath one would inherit it. `CLAUDE_PROJECT_DIR`
discriminates in neither direction: Copilot does not set it, and it was also
observed unset inside a Claude Code session, so its absence identifies
nothing.

Durable tests: `TestRecallOutputShapePerHost` in
`tests/test_memory_hook_registration.py`, which drives the registered command
under each host signal from a seeded isolated checkout, and `TestRenderForHost`
in `tests/test_memory_hook_recall.py`, which covers the precedence branch and
its control.

Unprobed, and left alone deliberately: the `SessionStart` dispatcher relay and
the `PreCompact` hook. Automatic-compaction delivery on Copilot is still
unmeasured (section 4 above), so the output channel there is moot until
someone probes it.

## 9. Re-running a probe

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
