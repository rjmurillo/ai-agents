---
name: agent-harness-reference
description: Field reference for how Claude Code and GitHub Copilot CLI actually behave. Hook stdin protocol and exit semantics, plugin root env vars, Copilot payload casing and kill budget, dispatch and frontmatter contracts, plugin resolution, MCP layer. Contract rows cite evidence and mark docs-say vs empirically-verified. Use when you say `harness contract`, `copilot cli hook behavior`, `hook payload format`. Do NOT use for the portability campaign itself (use `ai-agents-portability-campaign`).
version: 1.0.0
license: MIT
---

# Agent Harness Reference

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
A harness is the host program that runs the agent and its hooks: Claude Code
(Anthropic CLI) or GitHub Copilot CLI. This repo ships one plugin to both, and
the two harnesses disagree on working directory, matchers, payload field names,
timeouts, and frontmatter parsing. Twice, vendor docs were wrong by omission
and the gap shipped a P0 (issue #2205 wedged customers for 33 days; issue
#2290 blocked every tool call). This skill is the settled contract, row by
row, with the evidence grade for each claim. When a dimension is not in these
tables, do not reason by analogy: probe it (see
`ai-agents-empirical-probe-toolkit`).

## Triggers

- `harness contract`
- `copilot cli hook behavior`
- `hook payload format`
- `plugin root env var`
- `which hook events can block`

## Evidence Grades

Every contract row below carries one of these grades. The distinction exists
because both P0s above came from trusting an ungraded claim.

| Grade | Meaning | Trust level |
|-------|---------|-------------|
| EMPIRICAL | Measured by running the harness (probe plugin, env dump, stdin capture) against a pinned version | Highest. Re-verify on harness major version change |
| CODE | Encoded in this repo's committed code, config, or tests; read the cited path | High. The citation is the proof |
| REPO-ASSERTED | Stated in repo comments, ADRs, or memories without an independent probe recorded | Medium. Consistent with observed behavior, not separately measured |
| DOCS-SAY | Only source is vendor documentation | Lowest. Vendor docs omitted load-bearing facts twice (#2205, #2290) |

## Process

1. Identify the harness in play. Claude Code loads hooks from
   `.claude/settings.json` (dev, this repo) or from an installed plugin's
   `hooks/hooks.json`. Copilot CLI only loads the generated
   `src/copilot-cli/hooks/hooks.json`.
2. Look up the dimension (cwd, env, payload, timeout, matcher, frontmatter)
   in the tables below and honor the evidence grade.
3. If the dimension is missing or the grade is DOCS-SAY and your change is
   load-bearing, run an empirical probe first: install a probe plugin, dump
   env and stdin from inside a hook, use a pinned CLI version and a negative
   control. Method: `ai-agents-empirical-probe-toolkit`. Record the result in
   a Serena decision memory (pattern:
   `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md`).
4. Any change that alters a contract (launcher shape, env anchor, payload
   parsing) routes through `ai-agents-change-control` and must update
   `tests/build_scripts/test_generate_hooks_runtime_contract.py`. Treat
   launcher-shape changes as architecture per
   `.claude/rules/generated-artifacts.md`.

## Claude Code Hook Protocol

### Registration surfaces (as of 2026-07-19)

Two registrations exist and are kept in sync BY HAND. Drift between them is a
known weak point (see `ai-agents-architecture-contract`).

| Surface | Consumer | Shape (verified 2026-07-19) |
|---------|----------|-----------------------------|
| `.claude/settings.json` `hooks` key | Claude Code running in this repo | 7 events, 15 matcher groups: PreToolUse 7, SessionStart 2, PostToolUse 2, UserPromptSubmit 1, Stop 1, PreCompact 1, PermissionRequest 1 |
| `.claude/hooks/hooks.json` | Claude Code plugin install (project-toolkit) | Hand-ported twin: 6 events, 15 groups (no PreCompact); commands anchored as `python3 -u "${CLAUDE_PLUGIN_ROOT}/hooks/..."` |

Grade: CODE. Re-verify command in Provenance.

### Wire protocol

| Dimension | Contract | Grade | Evidence |
|-----------|----------|-------|----------|
| stdin | One JSON object per invocation; PreToolUse carries `tool_name` (string) and `tool_input` (parsed dict) | CODE | `build/scripts/generate_hooks_shim.py:315-325` reads `tool_name`/`toolName` and `tool_input`/`toolArgs` from the payload |
| Exit 0 | Allow. Plain stdout is injected as context (SessionStart, UserPromptSubmit); a JSON `{"systemMessage": ...}` on stdout is an advisory shown to the user | CODE | `.claude/hooks/SessionStart/invoke_context_loader.py:12-13,342` prints plain stdout for context injection; the `systemMessage` JSON form is a Claude Code harness affordance |
| Exit 2 | Block the action via exit 2. The block reason is surfaced on stderr (the agent-visible channel for PreToolUse blocks) and/or printed to stdout | CODE | `.claude/hooks/PreToolUse/invoke_security_gate.py:220-227,375-376` (block reason on stderr, exit 2); `invoke_retrospective_gate.py:325,327` (block reason on stdout, exit 2) |
| JSON decision payload | Alternative to exit 2: exit 0 plus `hookSpecificOutput.permissionDecision` (allow/deny/ask). The legacy top-level `{"decision":"deny"}` form is ignored by the harness | CODE | `invoke_security_commit_gate.py:16,168-171` documents that the exit-0 `{"decision":"deny"}` form was ignored, so the gate denies via `hookSpecificOutput.permissionDecision` or exit 2 |
| Exit codes vs ADR-035 | Claude hooks are EXEMPT from ADR-035 exit-code taxonomy; non-blocking hook types must exit 0 | CODE | Exit-code blocks in hook docstrings, e.g. `.claude/hooks/PreToolUse/invoke_security_gate.py:10` "exempt from ADR-035" |
| `CLAUDE_PLUGIN_ROOT` | Set by Claude Code to the plugin install dir; cwd is the USER working dir, not the plugin root | EMPIRICAL (Claude Code 2.1.159, session 1873) | ADR-071 "Verified Runtime Contract" section |
| Lib bootstrap | Hooks resolve shared lib via `CLAUDE_PLUGIN_ROOT` when set, else manifest walk-up to `.claude-plugin/plugin.json` | CODE | Bootstrap block in `.claude/hooks/PreToolUse/invoke_security_gate.py:24-42` (works in `.claude/` source tree and installed copies) |

### Which events can block

| Event | Can block? | Grade | Evidence |
|-------|-----------|-------|----------|
| PreToolUse | Yes (exit 2 or deny payload stops the tool call) | CODE | The 7 PreToolUse matcher groups in `.claude/settings.json` (registering 16 guard scripts under `.claude/hooks/PreToolUse/`) are built on this |
| UserPromptSubmit, Stop | Treated as blockable here; registered with guard semantics | REPO-ASSERTED | `.claude/settings.json` registrations; not separately probed |
| PostToolUse | Cannot undo the tool call; output is feedback only | REPO-ASSERTED | Hook docstrings; the tool already ran by definition |
| SessionStart | CANNOT block. "exit 2 only shows stderr as error" | REPO-ASSERTED | `.claude/hooks/SessionStart/invoke_memory_first_enforcer.py:17` and `invoke_session_initialization_enforcer.py:14` state it verbatim |

Matchers: each PreToolUse group carries a `matcher` (tool name, regex, or
glob) and Claude Code honors it, so only matching hooks run. Copilot CLI does
not (next section). That asymmetry drives the entire shim/dispatcher design.

## Copilot CLI Divergence Contract

The empirically settled table. Versions matter: env/cwd rows were measured
against GitHub Copilot CLI 1.0.57, payload rows against 1.0.58 (both Linux,
sessions 1873 and fix/2290). Re-probe on CLI major bumps.

| Dimension | Copilot CLI behavior | Grade | Evidence |
|-----------|---------------------|-------|----------|
| Hook cwd | USER working directory, NOT the plugin install dir. A bare `./hooks/...` path fails at the launcher with "No such file or directory" before any in-script handler runs | EMPIRICAL (1.0.57) | ADR-071 Verified Runtime Contract; `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md` (probe: `PWD=/tmp`, bare path exists=NO); retro `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md` |
| Env anchors | Exports `COPILOT_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT` (compat alias), and bare `PLUGIN_ROOT`, all set to the plugin install dir. NONE are in the vendor hooks reference (docs wrong by omission) | EMPIRICAL (1.0.57) | Same memory, env dump quoted in ADR-071 |
| Anchor pattern | bash: `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}`; PowerShell: `$(if ($env:COPILOT_PLUGIN_ROOT) {$env:COPILOT_PLUGIN_ROOT} else {$env:CLAUDE_PLUGIN_ROOT})`, symmetric fallback in both shells | CODE | `build/scripts/generate_hooks_emit.py:335-421` (`_build_copilot_entry`); executed under contract by `tests/build_scripts/test_generate_hooks_runtime_contract.py` with a bare-path negative control |
| Shell field choice | Linux honors only the `bash` field; Windows uses the `powershell` field (`py -3 -u`, not `python3`, for PATH reasons) | EMPIRICAL (1.0.57) / CODE | ADR-071 contract section; `_build_copilot_entry` docstring |
| Matchers | IGNORED. Every registered entry for an event runs on every occurrence. Filtering must happen in-process | EMPIRICAL (observed, issue #2295 session: all entries ran per tool call) | ADR-068 Context item 1 |
| Kill budget | Host kills a hook command at an observed 2-3 s; the killed process exits 143 (SIGTERM). `timeoutSec` in hooks.json does NOT raise the budget; it is host-controlled | EMPIRICAL (observed under load, Windows; not a pinned-version probe) | ADR-068 Context item 3 (measured ~246 ms cold start x 40 shims = ~8.7 s); `.serena/memories/copilot-hooks-observations.md` "exit 143 = SIGTERM (timeout kill)" |
| Failure policy | Non-zero exit or timeout fails the tool call CLOSED: "Denied by preToolUse hook (hook errored)" | EMPIRICAL (issue #2290 Five Whys step 1) | Retro `.agents/retrospective/2026-06-02-issue-2290-copilot-hook-payload-format.md` |
| Payload casing | Event key casing selects field names. camelCase event key sends `toolName` + `toolArgs` where `toolArgs` is a RAW JSON STRING (must `json.loads()`). PascalCase event key sends `tool_name` + `tool_input` as a parsed dict | EMPIRICAL (1.0.58, probe plugin stdin capture) | Retro 2290; `.serena/memories/copilot-hooks-observations.md` HIGH-confidence constraint |
| Repo's casing choice | `eventRemap` pins PascalCase target keys (`PreToolUse: PreToolUse`, etc.) so hooks receive snake_case; generated shims keep a dual-format fallback as insurance | CODE | `templates/platforms/copilot-cli.yaml:52-57`; dual-format shim shipped in PR #2293 |
| Event mapping | `Stop` remaps to `SessionEnd`; `SubagentStop`, `PermissionRequest`, `Notification`, `PreCompact` are DROPPED (no Copilot equivalent wired) | CODE | `templates/platforms/copilot-cli.yaml:52-62` (`eventRemap`, `eventDrop`) |
| Dispatcher | Generated tree ships ONE `_dispatch.py` per event (plus `_manifest.json`, `_bootstrap.py`); hooks.json has exactly one entry per event with per-event `timeoutSec` values (verified 2026-07-03: PreToolUse 695, PostToolUse 160, SessionStart 155, SessionEnd 90, UserPromptSubmit 66), and the dispatcher runs matched guards in-process via runpy | CODE (present in the committed tree as of 2026-07-03) | `src/copilot-cli/hooks/hooks.json` (5 events, 1 entry each); `src/copilot-cli/hooks/PreToolUse/_dispatch.py`; generator `build/scripts/generate_dispatcher.py` wired at `build/scripts/generate_hooks_events.py:381-385`. NOTE: ADR-068 status is still Proposed (as of 2026-07-02); the artifact exists, the ADR is not yet Accepted |
| Frontmatter parsing | Inline YAML arrays (`tools: ['a', 'b']`) fail on Windows Copilot CLI with "Unexpected scalar at node end". Block-style arrays only. `.agents/governance/PROJECT-CONSTRAINTS.md:220` additionally cites a CRLF-triggered parse failure as evidence; LF endings enforced repo-wide, deeper CRLF investigation tracked as repo issue #896 | EMPIRICAL (Windows user report, repo issue #893) | `.serena/memories/patterns/patterns-yaml-compatibility.md`; ADR-040 amendment (72 files converted); upstream github/copilot-cli#694 cited at `.agents/governance/PROJECT-CONSTRAINTS.md:220` alongside rjmurillo/ai-agents#893 (grade REPO-ASSERTED for the upstream number) |
| Install location | Installed plugins land under `~/.copilot/installed-plugins/...` (the dir containing `hooks/`) | EMPIRICAL (1.0.57 probe paths) | Env dump in `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md` |

Why the history matters: the FIRST #2205 fix assumed `COPILOT_PLUGIN_ROOT` by
analogy to `CLAUDE_PLUGIN_ROOT` and shipped unverified (it happened to be
right; the method was wrong). ADR-071's probe then verified env and cwd but
NOT stdin, and the stdin gap became #2290 the next day. A 15-minute probe is
cheaper than a P0. Full incident chronicle: `ai-agents-failure-archaeology`.

## Skill, Agent, Command Dispatch

Everything dispatches by STRING NAME, not imports: "no caller found" does not
mean dead code. Design rationale lives in `ai-agents-architecture-contract`.

| Surface | Invoked via | File contract | Grade / evidence |
|---------|------------|---------------|------------------|
| Skill (Claude Code) | Skill tool by name | `.claude/skills/NAME/SKILL.md`, frontmatter MUST have `name`, `version`, `description` | CODE: `.claude/rules/claude-agents.md` MUST 2; schema detail `.agents/steering/claude-skills.md`; validator `.claude/skills/SkillForge/scripts/validate-skill.py` (see `SkillForge`) |
| Slash command (Claude Code) | `/name` | `.claude/commands/NAME.md`, frontmatter keys observed: `description`, `allowed-tools`, `argument-hint` | CODE: `.claude/commands/build.md:1-5` |
| Subagent (Claude Code) | Task tool `subagent_type` by name | Generated from `templates/agents/NAME.shared.md` (canonical) via `python3 build/generate_agents.py` into `src/vs-code-agents/` and `src/copilot-cli/agents/` | CODE: generator tree verified; per-tree detail in `ai-agents-generation-and-release` |
| Agent (Copilot CLI) | Agent name | `src/copilot-cli/agents/NAME.agent.md`, frontmatter: `name`, `description`, `argument-hint`, `tools` as a BLOCK-STYLE list (inline arrays break Windows parsing, row above) | CODE: `src/copilot-cli/agents/analyst.agent.md:1-12` |
| Hook (both) | Event occurrence | Registration surfaces per harness (tables above) | CODE |

Skill-first bias: ADR-030 measured direct MCP/skill calls at 5-20 ms vs
100-200 ms Task subagent overhead (`ADR-030-skills-pattern-superiority.md`,
comparison table). Grade REPO-ASSERTED (numbers recorded in the ADR, not
re-measured here).

## Plugin Resolution (as of 2026-07-03)

| Manifest | Serves | Contents |
|----------|--------|----------|
| `.claude-plugin/marketplace.json` (repo root) | Claude Code marketplace | `claude-agents` from `./src/claude`; `project-toolkit` from `./.claude` (the dev tree IS the Claude plugin source) |
| `.github/plugin/marketplace.json` | Copilot CLI marketplace | `project-toolkit` from `./src/copilot-cli` (generated tree) |
| `.claude/.claude-plugin/plugin.json` | project-toolkit for Claude Code | version 0.5.254 |
| `src/copilot-cli/.claude-plugin/plugin.json` | project-toolkit for Copilot CLI | version 0.5.254 |
| `src/claude/.claude-plugin/plugin.json` | claude-agents plugin (hand-synced tree, ADR-036) | version 0.3.29 |

Grade: CODE, all read 2026-07-03. Rule: any content change under `.claude/`,
`src/claude/`, or `src/copilot-cli/` requires a strictly-greater semver bump
of that tree's plugin.json, enforced by a push hook plus
`.github/workflows/validate-plugin-version-bump.yml` (stale-cache incident,
PR #1942). Full flag/marker semantics: `ai-agents-config-catalog`.

## MCP Layer

MCP (Model Context Protocol) servers give the harness extra tools. Configured
in `.mcp.json` (read 2026-07-03):

| Server | Transport | What breaks when absent |
|--------|-----------|-------------------------|
| serena | stdio, `uvx --from git+https://github.com/oraios/serena ... --context claude-code --port 24282` | Symbol navigation and canonical memory (ADR-007) |
| deepwiki | http, `https://mcp.deepwiki.com/mcp` | External repo Q&A only; no gate depends on it |
| forgetful | stdio, `uvx forgetful-ai` | Supplementary memory tier (ADR-007: Serena canonical, Forgetful supplementary); `memory` and `memory-search` degrade to Serena-only |

Constraint: subagents cannot reach MCP tools; pre-resolve symbols (file:line)
into delegation prompts (`.claude/rules/lsp-first.md`). Grade: CODE.

## Anti-Patterns

| Anti-pattern | Why it burns you | Do instead |
|--------------|------------------|------------|
| Assuming a runtime contract by analogy ("Claude sets CLAUDE_PLUGIN_ROOT, so Copilot sets COPILOT_PLUGIN_ROOT") | The first #2205 fix did exactly this and shipped unverified; only luck made it correct | Probe under the real harness, pinned version, negative control (`ai-agents-empirical-probe-toolkit`) |
| Trusting vendor docs for load-bearing behavior | Docs omitted the plugin root env vars AND the payload casing rule; both gaps became P0s | Grade the claim; upgrade DOCS-SAY to EMPIRICAL before depending on it |
| Self-referential tests (generator output string-matched against itself) | Proved "internal consistency, not runtime correctness"; shipped the #2290 payload gap | Runtime-contract test: foreign cwd, contract env, execute the artifact, include a case that CAN fail |
| Camel/snake payload guessing in hook code | Field names depend on event-key casing; wrong guess = every tool call denied | Pin PascalCase in `eventRemap`; keep the dual-format fallback shim |
| Raising `timeoutSec` to beat the Copilot kill budget | The budget is host-controlled; hooks.json cannot raise it | Cut work per invocation (per-event dispatcher, in-process matching) |
| Editing `src/copilot-cli/hooks/` by hand | It is a generated tree; drift gates go red and the next regeneration erases you | Edit `.claude/hooks/` sources, regenerate (`ai-agents-generation-and-release`) |
| Launcher-level fail-open wrappers | Converts a loud failure into a silently disabled hook (rejected, issue #2230) | Prevention gates plus loud failure per `.claude/rules/generated-artifacts.md` |

## Verification

Run before relying on or updating any row in this reference:

- [ ] Registration counts still match: `uv run python -c "import json; h=json.load(open('.claude/settings.json'))['hooks']; print({k: len(v) for k, v in h.items()})"` shows 7 events / 15 total groups (else update the Claude table)
- [ ] Copilot anchor pattern unchanged: `grep -n 'COPILOT_PLUGIN_ROOT' build/scripts/generate_hooks_emit.py` still shows the bash fallback form
- [ ] Runtime-contract suite green: `uv run pytest tests/build_scripts/test_generate_hooks_runtime_contract.py -q` (Linux authoritative; one test is known-broken on Windows)
- [ ] Dispatcher still one-entry-per-event: `uv run python -c "import json; h=json.load(open('src/copilot-cli/hooks/hooks.json'))['hooks']; print({k: len(v) for k, v in h.items()})"` shows 1 per event
- [ ] Any NEW contract dimension you relied on has an EMPIRICAL row backed by a decision memory naming the CLI version probed

## Provenance and Maintenance

Verbatim probe measurements behind the tables:
`references/probe-evidence.md` (quotes ADR-071 env dump, the payload casing
capture, and the ADR-068 timing numbers, plus the minimum bar for re-probing).

Authored 2026-07-03 against the working tree. Retro-cited short SHAs do not
resolve locally even with full history present (~1471 commits as of
2026-07-03); the retros and memories cited are the durable record.

Sources (path:line where load-bearing):

- ADR-071 `.agents/architecture/ADR-071-plugin-hook-runtime-contract-verification.md` (Verified Runtime Contract: Copilot 1.0.57, Claude Code 2.1.159, env dump quote); status Accepted 2026-06-02
- ADR-068 `.agents/architecture/ADR-068-consolidated-hook-dispatcher.md` (matcher ignoring, 2-3 s kill, 246 ms cold start); status Proposed as of 2026-07-02
- `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md` (probe evidence, docs wrong by omission)
- `.serena/memories/copilot-hooks-observations.md` (payload casing, exit 143, toolArgs JSON string)
- `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md` and `2026-06-02-issue-2290-copilot-hook-payload-format.md`
- `build/scripts/generate_hooks_emit.py:335-421`; `build/scripts/generate_hooks_events.py:381-385`; `templates/platforms/copilot-cli.yaml:52-62`
- `.claude/rules/generated-artifacts.md`; `.claude/rules/lsp-first.md`; `.claude/rules/claude-agents.md` (MUST 2)
- `build/scripts/generate_hooks_shim.py:315-325`; `.claude/hooks/SessionStart/invoke_memory_first_enforcer.py:17`
- Manifests and `.mcp.json` read directly 2026-07-03

Re-verification one-liners for volatile facts:

- Plugin versions: `uv run python -c "import json; [print(p, json.load(open(p)).get('version')) for p in ['.claude/.claude-plugin/plugin.json', 'src/claude/.claude-plugin/plugin.json', 'src/copilot-cli/.claude-plugin/plugin.json']]"`
- Event remap/drop: `grep -n -A 10 'eventRemap' templates/platforms/copilot-cli.yaml`
- ADR-068/072 status: `grep -n -A 2 '## Status' .agents/architecture/ADR-068-consolidated-hook-dispatcher.md .agents/architecture/ADR-072-jtbd-plugin-architecture.md`
- SessionStart cannot-block assertion: `grep -rn 'cannot block' .claude/hooks/SessionStart/`
- Probe a live CLI (the only real re-verification): follow `ai-agents-empirical-probe-toolkit` recipe 1 and update the decision memory with the new version number

Known unverified items (flagged inline above): SessionStart non-blocking
(repo-asserted only); exact Copilot kill budget (observed 2-3 s,
version-dependent, no pinned probe); Copilot fail-closed policy (observed,
not vendor-documented).
Triage help for these failure classes: `ai-agents-debugging-playbook`.
