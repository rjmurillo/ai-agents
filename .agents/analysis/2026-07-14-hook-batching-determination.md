---
status: determined
priority: high
blocking: false
---

# Hook Performance and Effectiveness Review

## Decision

The current hook set costs too much on Windows. When hooks make Copilot CLI
unusable, use `disableAllHooks` as a version-specific kill switch and accept the loss of
repository, user, and plugin hook execution. A selective minimal profile for
GPT-5.6 Sol and Opus 4.8 is the durable hypothesis, pending controlled A/B
validation.

Copilot CLI 1.0.70 provides one immediate performance switch:

```json
{
  "disableAllHooks": true
}
```

This switch is broader than the local help text suggests. In a controlled,
trusted-worktree probe, it stopped repository and plugin hook execution. Policy
hooks still loaded and remain exempt by contract. Treat this as a version-specific
kill switch, not a selective plugin profile.

No supported setting was found that disables repository hooks while retaining
plugin hooks. The durable fix needs hook profiles inside the plugin dispatcher,
not another host-side process multiplexer.

## Measured cost

The repository registers 53 command hooks in `.claude/settings.json`, covering
48 unique scripts.

| Event | Matcher groups | Command registrations |
| --- | ---: | ---: |
| PreToolUse | 11 | 29 |
| SessionStart | 2 | 7 |
| UserPromptSubmit | 1 | 4 |
| PostToolUse | 5 | 7 |
| Stop | 1 | 3 |
| SubagentStop | 1 | 1 |
| PreCompact | 1 | 1 |
| PermissionRequest | 1 | 1 |

The generated Copilot plugin reduces host process creation to one dispatcher per
event. Its manifests still route 49 shim entries: 29 PreToolUse, 7 PostToolUse,
6 SessionStart, 4 UserPromptSubmit, and 3 SessionEnd.

ADR-068 records a Windows Python cold start near 246 ms and a sequential
aggregate near 8.7 seconds in the prior per-shim Copilot layout. The dispatcher
removed that spawn storm for the plugin path. It did not remove the cost of
executing the shim bodies.

A same-prompt probe in the trusted review worktree produced these results:

| Profile | Total CLI time | Repository marker | Hook output |
| --- | ---: | ---: | ---: |
| Hooks enabled | 71,742 ms | 1 | 20 lines |
| `disableAllHooks` | 26,994 ms | 0 | 0 lines |

The 44,748 ms difference is not a clean hook benchmark because model latency
varies. The hook trace is the stronger evidence. In the enabled run, hook loading
started at 00:07:31 and the repository marker completed at 00:08:28. In the
disabled run, no repository or plugin hook output appeared. A second disabled
probe that called PowerShell also produced zero hook output while the CLI logged
five policy hooks and twelve hooks from three plugins as loaded.

Loading is not execution. Under `disableAllHooks`, plugin metadata still loaded,
but plugin hook commands did not run.

### Probe method

The enabled probe added this temporary repository hook in the trusted worktree:

```json
{
  "version": 1,
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "powershell": "Write-Output 'REPO_HOOK_FILE_MARKER'"
      }
    ]
  }
}
```

Both runs used the same worktree, prompt, plugin directory, and CLI flags:

```text
copilot --plugin-dir src\copilot-cli --log-dir <DIR> --log-level all \
  -p "Reply PROBE." --allow-all-tools
```

The disabled run added only `{"disableAllHooks": true}` to
`.github/copilot/settings.local.json`. Relevant log evidence:

```text
enabled  00:07:31 Loaded 5 policy hook(s) from 1 document(s)
enabled  00:07:31 Loaded 12 hook(s) from 3 plugin(s)
enabled  00:08:28 [hook stdout] REPO_HOOK_FILE_MARKER
enabled  hook stdout/stderr lines: 20

disabled 00:08:43 Loaded 5 policy hook(s) from 1 document(s)
disabled 00:08:43 Loaded 12 hook(s) from 3 plugin(s)
disabled hook stdout/stderr lines: 0
```

A second disabled run required one PowerShell tool call and again counted zero
lines matching `\[hook (stdout|stderr)\]`.

## Effectiveness by hook type

| Hook type | Outcome value | Cost judgment | Recommended placement |
| --- | --- | --- | --- |
| Security, branch, commit, push, and permission gates | High for every model | Worth paying at the protected boundary | Keep, but run only when the guarded action occurs |
| Context and memory injection | Lower marginal value for GPT-5.6 Sol and Opus 4.8 | Repeated process and token cost is not justified | Load once per session or on explicit retrieval |
| Skill-first, research, and LSP routing nudges | Useful when a model selects the wrong path | Current repeated checks tax compliant calls | Check only on a detected violation or use static instructions |
| Session initialization | Session context, not per-tool reasoning | Startup work blocks the first response | Keep one bounded session hook |
| Session logging | Audit continuity | Repeated checks duplicate guidance | Use explicit session lifecycle commands |
| Retrospective automation | Learning capture | Stop-time mutation changed the tree during probes | Use an explicit session-end command |
| Auto-lint, ADR sync, and plan-state sync | Useful after mutations | Too broad when attached to every write | Batch at commit, push, or explicit validation |
| Error and observation hooks | Useful for diagnosis | Low direct effect on answer quality | Keep only if they are non-blocking and cheap |

The hard gates prevent damage that model intelligence cannot make impossible.
Advisory hooks mainly repeat instructions already present in repository and user
context. Their value falls as instruction following and context capacity improve.

## Model-tier recommendation

No controlled cross-model hook A/B test exists. The following assessment is
qualitative and should be tested before becoming policy. These are manual
selection candidates, not automatic routing rules.

| Model tier | Candidate manual profile | Reason |
| --- | --- | --- |
| GPT-5.6 Sol and Opus 4.8 | Minimal | Keep policy and irreversible-action gates. Disable repeated advisory injection and lifecycle automation. |
| Sonnet, Terra, and Luna | Balanced | Keep one session context load, routing checks on violations, and hard gates. Skip duplicate per-tool reminders. |
| Haiku and small-context models | Full, with a strict time budget | More context injection may help, but slow hooks still destroy usability and can cause false denials. |

Do not auto-detect model tier inside a hook until the runtime exposes a stable,
verified model field. An explicit profile is easier to test and reason about.
Suggested profiles are `minimal`, `balanced`, and `full`.

## Windows defects observed

The enabled probe exposed failures that add latency without improving outcomes:

- `context-loader` failed to encode U+1F504 through the Windows character map.
- Plugin path validation rejected the worktree through `CLAUDE_PROJECT_DIR`.
- The skill-learning hook emitted `E_CWE22_PROJECT_DIR_MISMATCH`.
- Skill pattern loading failed because `skill_pattern_loader` was not importable.
- Session-log guidance appeared three times.
- A Stop hook created retrospective files and modified the retrospective index
  during a measurement run.

These are correctness defects, not only performance defects. A hook that fails,
duplicates work, or mutates the tree during a probe creates customer cost with no
reliable policy benefit.

## Configuration guidance

For an immediate Windows workaround, create
`.github/copilot/settings.local.json` with `disableAllHooks` set to `true`, then
start a new Copilot CLI session. The setting is read at session startup. This
repository does not ignore that file, so add it to `.git/info/exclude` or use a
user-level setting when the scope is intentional.

Tradeoff: repository, user, and plugin hooks stop executing. Policy hooks remain.
Skills, agents, and instructions are separate plugin surfaces and continue to
load.

Do not use a broad Defender exclusion as the default fix. It weakens malware
inspection and only reduces the cost of each process. It does not fix the number
of processes or the failing hook bodies. A managed, narrow exclusion can be an
operator decision after the hook count is reduced.

## Rejected code path

A Claude-side in-process dispatcher was built and then reverted. Independent
review found that it concatenated multiple JSON outputs, changed blocking event
behavior, replaced host concurrency with serial execution, invented timeout
budgets, lacked generator ownership, and could recurse after regeneration. Its
speed result measured a different contract and was not valid evidence.

A safe multiplexer would need one final protocol object, explicit merge rules,
event-correct blocking behavior, per-hook timeout semantics, and runtime tests
with negative controls. That work is larger and riskier than adding profiles to
the existing Copilot dispatcher.

## Recommended order

1. Document `disableAllHooks` as the version-specific Windows kill switch for frontier
   models. State that it disables plugin hook execution in CLI 1.0.70.
2. Add explicit `minimal`, `balanced`, and `full` profiles to the existing
   Copilot dispatcher. Default Windows frontier sessions to `minimal` only after
   measured A/B validation.
3. Keep hard gates at commit, push, permission, and security boundaries. Move
   advisory work out of per-tool paths.
4. Fix the Windows encoding, project-root validation, import, and duplicate
   session guidance defects before calling the full profile supported on Windows.
5. Run controlled task suites with hooks on and off for GPT-5.6 Sol, Opus 4.8,
   Sonnet, Terra, Luna, and Haiku. Measure success rate, false denials, hook wall
   time, process count, and tokens added.

## Evidence

- `.claude/settings.json`
- `src/copilot-cli/hooks/*/_manifest.json`
- `.agents/architecture/ADR-068-consolidated-hook-dispatcher.md`
- `.claude/lib/hook_dispatch.py`
- GitHub hooks reference: <https://docs.github.com/en/copilot/reference/hooks-reference>
- Copilot CLI configuration reference:
  <https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference>
- Raw Copilot CLI 1.0.70 probe logs are uncommitted session artifacts under
  session `0276d4e1-f1fd-40f7-a71f-ce0e0a51d719`. The measured counts and
  timestamps needed for this determination are recorded above.
