# ADR Debate Log: ADR-107 amendment, read-only agent tool grants

## Summary

- **Rounds**: 3 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-107-debate-log.md`
- **Outcome**: Consensus
- **Final Status**: proposed (the amendment changes no ADR status)
- **Scope**: the "Amendment 2026-10-17" section of ADR-107 and the code on branch `feat/readonly-agents-deny-table`.
- **Panel**: full six-agent panel. The change touches agent tool contracts, the parity gate, and the renderer, which other gates read.

## Owner decisions in force

The owner made these decisions on 2026-10-17. Reviewers could flag a false premise but not argue preference.

- **D2**: read-only agents must reach MCP tools whose names vary by harness and config source.
- **D3**: the deny list enforces only the #5356 invariant: no shell and no local file mutation.
- **D4** (made after round 1): replace inherit-all with a `tools:` allowlist of built-ins plus per-server MCP grants.
- **Standing rule**: no agent loses a capability it held on main.

## Round 1 Summary

Round 1 reviewed the inherit-all design. The four agents had no `tools:` key and used `disallowedTools` for `Bash`, `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, and 13 Serena tools.

### Key Issues Addressed

- P0 (architect): the ADR frontmatter says `status: proposed` and `implemented: false`, but the amendment described enforced behavior.
- P0 (critic, security): inherit-all exposed shell-capable tools that the deny list never named. These were `PowerShell`, `Monitor`, `Skill`, the cron tools, `RemoteTrigger`, and the context-mode `ctx_execute` tools. The #5356 no-shell invariant did not hold.
- P1: there were no Considered Options and no ADR-097 or ADR-109 citation. The byte figures had no anchor. The claim "main session has the same exposure" overstated parity. Background mode was not covered. The tests did not pin the invariant. The Chesterton's Fence history and a rollback clause were missing.

### Major Changes Made

- The owner chose D4 after headless probes on Claude Code 2.1.302. The probes used `claude -p --agents` with throwaway agent definitions on 2026-10-17.
- Probe results, quoted from the probe output:
  - `probe-deny` had no `tools:` key and denied `Bash`, `Edit`, `Write`, `MultiEdit`, `NotebookEdit`. Its result line: `HAS_BASH=no, HAS_POWERSHELL=no, HAS_MONITOR=yes, HAS_WRITE=no, HAS_CTX_EXECUTE=yes, MCP_COUNT=197`.
  - `probe-allow` had `tools: [Read, Glob, Grep]`. It saw `TOOLS=Read,Glob,Grep` and `MCP_COUNT=0`.
  - `probe-hybrid` had `tools: [Read, Glob, Grep, ToolSearch, mcp__*]`. It saw `TOOLS=Read,Glob,Grep` only, so the global `mcp__*` grants nothing.
  - `probe-server-wild` had `tools: [Read, ToolSearch, mcp__claude_ai_Context7__*, mcp__claude_ai_hindsight]`. It saw 43 tools, including `mcp__claude_ai_Context7__query-docs` and `mcp__claude_ai_hindsight__cancel_operation`.
  - `probe-deny-more` denied 11 built-ins and the context-mode server. It still saw `CronCreate`, `CronDelete`, `CronList`, `RemoteTrigger`, `PushNotification`, and `DesignSync`.
- Then the implementation moved Serena to per-tool grants. A wildcard plus a deny list re-creates the deny-list flaw inside one server.
- Cursor copies were kept. `readonly: true` only narrows an agent.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Block: status and frontmatter contradicted the amendment |
| critic | Block: inherited shell-capable tools |
| independent-thinker | Disagree-and-Commit: exposure overstated, background mode, missing options |
| security | Block: #5356 invariant broken by inherited executors |
| analyst | Accept: every numeric claim verified |
| high-level-advisor | Disagree-and-Commit: Chesterton's Fence, rollback, dispatch alternative |

## Round 2 Summary

Round 2 reviewed the D4 design at commit `d775104c0e`. Each agent holds its main built-ins plus `ToolSearch`. Serena, GitHub, and DeepWiki keep their per-tool grants from main. Context7 is granted by server wildcard under three prefix variants.

### Key Issues Addressed

- All round 1 P0s are resolved. No allowlist holds an executor. Only `security` holds `Write`, as on main. The amendment states it changes no ADR status.
- Independent-thinker P1: can `ToolSearch` surface a tool outside the allowlist? A probe agent had `tools: [Read, ToolSearch, mcp__claude_ai_Context7__*]`. It ran `ToolSearch` for `select:Bash`, `ctx_execute`, and `select:mcp__claude_ai_Slack__slack_send_message`. Each returned "No matching deferred tools found", and nothing ungranted was callable.
- Critic P1: the tests checked exact forbidden names only. A literal `Cron*` or an extra server wildcard would pass.
- High-level-advisor P1: `$deny:` renderer support had no present user.
- Analyst P1: the byte budget cited no head SHA. Three probe claims overstated the probe output.

### Major Changes Made

- A subset test pins each rendered `tools:` list to its main allowlist, plus `ToolSearch` and the analyst Context7 wildcards.
- `$deny:` support and its tests are removed.
- The amendment title now names Context7 as the only wildcard. The byte budget cites the head commit.
- The probe claims now match the probe output: default Agent launch settings, 11 built-ins denied, and connector names Context7, hindsight, and Claude_Docs.
- Residual risk adds name squatting on a `context7` server in `.mcp.json`. It also adds Context7 query egress.
- The amendment records that the probe evidence comes from Claude Code 2.1.302 only.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. P2: rename the title, align the YAML header |
| critic | Disagree-and-Commit: add the subset test |
| independent-thinker | Disagree-and-Commit: resolve the ToolSearch question |
| security | Accept. P2: ToolSearch negative control, name squatting note |
| analyst | Disagree-and-Commit: cite the head SHA, fix probe claims |
| high-level-advisor | Disagree-and-Commit: drop `$deny:` as YAGNI |

### Dissent recorded

- High-level-advisor: the change is large for its net value. The gains are `ToolSearch`, Context7 under connector spellings, and the `$mcp:` renderer. GitHub still uses one prefix. F5 and F6 sit about 800 bytes under their ceilings, so the next edit will trip them.
- Independent-thinker: one harness version is not a CI pin. A new Claude Code release can change the probed behavior.

## Round 3 Summary

Round 3 took PR #6700 review comments on head `7f3a0351e7`. The six-agent panel did not reconvene. The changes are corrections inside the agreed design.

### Key Issues Addressed

- A PR reviewer found that the baseline sentence did not add up. The diff shows three `capability:builtin` digests changing, and analyst's `capability:mcp:context7` pin replaced by a new `capability:builtin` pin. That keeps the count at 109.
- CodeRabbit found that the Cursor copy treated any `mcp__<server>__*` as read-only. A future `mcp__github__*` would have earned `readonly: true`.
- Checking that finding showed the renderer did not enforce `explicit_only`. A template writing `$mcp:serena` would have rendered `mcp__serena__*`, and that grants `execute_shell_command`.

### Major Changes Made

- `expand_server_grant` fails for a server marked `explicit_only` or `remote_only`.
- `is_readonly_tool` accepts only the exact wildcards the table allows. Tests cover Serena, GitHub, DeepWiki, Slack, and two lookalike Context7 spellings.
- The amendment's baseline sentence now matches the diff.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Not reconvened; round 2 Accept stands |
| critic | Not reconvened; round 2 dissent addressed |
| independent-thinker | Not reconvened; round 2 dissent addressed |
| security | Not reconvened; round 2 Accept stands, and these changes narrow grants |
| analyst | Not reconvened; round 2 dissent addressed |
| high-level-advisor | Not reconvened; round 2 dissent stands as recorded |

### Next Steps

Ship the branch as one PR. A later change that adds GitHub or DeepWiki connector spellings needs byte headroom first.
