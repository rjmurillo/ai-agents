---
status: determined
priority: high
blocking: false
---

# Hook Performance and Effectiveness Review

## Decision

The current hook set costs too much on Windows. When hooks make Copilot CLI
unusable, use `disableAllHooks` only through an approval-required, time-bounded,
read-only diagnostic procedure. This accepts the loss of repository, user, and
plugin hook execution. A selective minimal profile for GPT-5.6 Sol and Opus 4.8
is an analytical hypothesis only. The current roadmap places Copilot CLI in
maintenance-only mode, so profile feature work requires formal reprioritization.
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
plugin hooks. The maintenance path is to fix failing Windows hooks and remove or
rescope advisory work from repeated event paths.

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
aggregate near 8.7 seconds in the prior per-shim Copilot layout. ADR-068 remains
Proposed. The generated dispatcher exists, but its parity claims are not an
accepted decision. The dispatcher removed that spawn storm for the plugin path.
It did not remove the cost of executing the shim bodies.

A same-prompt probe in the trusted review worktree produced these results:

| Profile | Total CLI time | Repository marker | Hook output |
| --- | ---: | ---: | ---: |
| Hooks enabled | 71,742 ms | 1 | 20 records, 8,665 logged bytes |
| `disableAllHooks` | 26,994 ms | 0 | 0 records |

The 44,748 ms difference is not a clean hook benchmark because model latency
varies. The hook trace is the stronger evidence. In the enabled run, hook loading
started at 00:07:31 and the repository marker completed at 00:08:28. The log also
contained the `PONYTAIL MODE ACTIVE` marker emitted by the installed Ponytail
plugin. In the disabled run, neither marker appeared and no hook output was
recorded. A second disabled probe that called PowerShell also produced zero hook
output while the CLI logged five policy hooks and twelve hooks from three plugins
as loaded.

Loading is not execution. Under `disableAllHooks`, plugin metadata still loaded,
but the enabled run's plugin marker did not appear. The 20 enabled log records
contained 7,725 payload bytes after removing timestamps and log prefixes. The
largest payload was 5,393 bytes. Token volume was not measured.

The probe did not record Defender service state, process count, or compare
Defender on and off. It records an end-to-end Windows difference correlated with
hook execution. It does not isolate hook duration or Defender's share.

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
enabled  00:08:28 [hook stdout] PONYTAIL MODE ACTIVE
               source: installed Ponytail plugin only
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
qualitative and should be tested before becoming policy. These are analytical
candidates, not automatic routing rules or approved implementation work.

| Model tier | Analytical candidate | Reason |
| --- | --- | --- |
| GPT-5.6 Sol and Opus 4.8 | Minimal | Keep policy and irreversible-action gates. Disable repeated advisory injection and lifecycle automation. |
| Sonnet, Terra, and Luna | Balanced | Keep one session context load, routing checks on violations, and hard gates. Skip duplicate per-tool reminders. |
| Haiku and small-context models | Full, with a strict time budget | More context injection may help, but slow hooks still destroy usability and can cause false denials. |

Do not implement model-tier profiles while Copilot CLI remains maintenance-only.
If the roadmap reopens feature work, validate explicit `minimal`, `balanced`,
and `full` profiles before considering automatic routing.

## Windows defects observed

The enabled probe exposed failures that add latency without improving outcomes:

- `context-loader` failed to encode U+1F504 through the Windows character map.
- Plugin path validation rejected the worktree through `CLAUDE_PROJECT_DIR`.
- The skill-learning hook emitted `E_CWE22_PROJECT_DIR_MISMATCH`.
- Skill pattern loading failed because `skill_pattern_loader` was not importable.
- Session-log guidance appeared three times.
- A Stop hook created `.agents/retrospective/2026-07-15-auto-retro.md` and
  changed `.agents/retrospective/INDEX.md` in the review worktree during a
  measurement run. The index was restored, and the skeleton was moved to session
  artifact storage.

These are correctness defects, not only performance defects. A hook that fails,
duplicates work, or mutates the tree during a probe creates customer cost with no
reliable policy benefit.

## Configuration guidance

For temporary diagnostic recovery on Windows, an owner or security approver can
run a read-only session with `.github/copilot/settings.local.json` setting
`disableAllHooks` to `true`. Start a new Copilot CLI session because settings are
read at session startup. Do not mutate files, commit, or push in that session.

Do not hide this file through `.git/info/exclude`. Keep the bypass visible in
`git status`, record why it was enabled, and remove it after the diagnostic
session. In managed environments, use an auditable launcher or policy-approved
profile with an expiry.

Tradeoff: repository, user, and plugin hooks stop executing. Policy hooks remain.
Skills, agents, and instructions are separate plugin surfaces and continue to
load. Remove the setting and start a hook-enabled session before any mutation,
commit, or push.

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
with negative controls. That work is larger and riskier than pruning or
rescoping the existing hook set.

## Recommended order

1. Document `disableAllHooks` as an approval-required, time-bounded, read-only
   diagnostic procedure. State that it disables plugin hook execution in CLI 1.0.70 and must
   not become a default developer setting.
2. Fix the Windows encoding, project-root validation, import, and duplicate
   session-guidance defects.
3. Keep hard gates at commit, push, permission, and security boundaries. Remove
   or rescope existing advisory work from per-tool paths as a performance fix.
4. Run controlled task suites with hooks on and off for GPT-5.6 Sol, Opus 4.8,
   Sonnet, Terra, Luna, and Haiku. Measure success rate, false denials, hook wall
   time, process count, and tokens added.
5. Do not add a dispatcher profile framework while Copilot CLI remains
   maintenance-only. Reopen that decision only through roadmap approval.

## Evidence

- `.claude/settings.json`
- `src/copilot-cli/hooks/*/_manifest.json`
- `.agents/architecture/ADR-068-consolidated-hook-dispatcher.md`
- `.claude/lib/hook_dispatch.py`
- GitHub hooks reference: <https://docs.github.com/en/copilot/reference/hooks-reference>
- Copilot CLI configuration reference:
  <https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference>
- Raw Copilot CLI 1.0.70 probe logs are uncommitted session artifacts under
  session `0276d4e1-f1fd-40f7-a71f-ce0e0a51d719`. The sanitized counts,
  timestamps, byte sizes, and markers needed for this determination are recorded
  above.
- Enabled raw log SHA-256:
  `EA0E1E8D60F36D8688D45BF8C3466223AF25CBCB7DF8ECF39BF37F44CCA62FD3`.
- Disabled raw log SHA-256:
  `0BAA9F5A4E2F4CABD0C24C2F16684CECEB1F374726C0CD4EB700A8AD76A041CE`.
- Disabled real-tool raw log SHA-256:
  `ABF4599919FD22DD9F413FFEA1487B99DABE0F69DF87DE4370F4B6EA070091BC`.
