---
name: ai-agents-architecture-contract
description: Load-bearing design decisions for this repo as a contract you check before changing anything. Covers the asymmetric generation seam, source-of-truth per tree, hook runtime failure policy, memory tiers, plugin surfaces, invariants, and known-weak points. Use when you say `which tree is canonical`, `architecture contract`, `why is this designed this way`. Do NOT use for operating the build pipeline (use `ai-agents-generation-and-release`) or CI triage (use `ai-agents-debugging-playbook`).
version: 1.0.0
license: MIT
---

# AI Agents Architecture Contract

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
This skill is the map of design decisions that hold this repository up: what is canonical, what is generated, which invariants are enforced by gates, and where the structure is honestly weak. Read it before any change that touches more than one tree, any hook, any plugin surface, or any generated file. The repo's governance is verification-based, not trust-based (`.agents/SESSION-PROTOCOL.md:30`: "This protocol uses **verification-based enforcement**"), so almost every claim below is backed by a gate you can run.

## Triggers

- `which tree is canonical`
- `architecture contract`
- `why is this designed this way`
- `what invariant am I about to break`
- `where is the source of truth for this file`

## Process

### Phase 1: Locate the source of truth before touching any file

The generation seam is ASYMMETRIC. There is no single "templates in, everything out" pipeline. Two seams coexist (ADR-072, status Proposed, corrected this premise explicitly: "the seam is asymmetric"):

1. Agents: `templates/agents/*.shared.md` is canonical; the outputs under `src/` are generated.
2. Rules, skills, commands, hooks: `.claude/` itself is canonical (Claude Code consumes it directly); generators emit mirrors for other harnesses.

Source-of-truth table (verified against `.agents/governance/GENERATOR-FILES.md` and `build/scripts/build_all.py` GENERATORS list at line 426; 7 generators: agents, agent-catalog, skills, commands, rules, lib, hooks):

| Artifact class | Canonical source (edit here) | Generated or mirrored output (never edit) | Mechanism |
|---|---|---|---|
| Agents (Copilot CLI, VS Code) | `templates/agents/*.shared.md` | `src/copilot-cli/agents/`, `src/vs-code-agents/` | `build/generate_agents.py` per `templates/platforms/*.yaml` `outputDir` |
| Agents (Claude Code) | `src/claude/*.md` is itself canonical, hand-written | none; `.claude/agents/` is a hand-maintained sibling copy | MANUAL dual edit (ADR-036, Accepted); `templates/README.md:131`: "**Also edit**: `src/claude/{agent}.md` (MANUAL - not auto-synced!)" |
| Rules | `.claude/rules/*.md` | `.github/instructions/`, `src/copilot-cli/instructions/` | `build/scripts/generate_rules.py` |
| Skills | `.claude/skills/<name>/` | `src/copilot-cli/skills/<name>/` | `build/scripts/generate_skills.py` |
| Commands | `.claude/commands/<name>.md` | `src/copilot-cli/skills/<name>/SKILL.md` | `build/scripts/generate_commands.py` |
| Hooks | `.claude/hooks/` plus `.claude/settings.json` | `src/copilot-cli/hooks/` plus its `hooks.json` | `build/scripts/generate_hooks.py` (plus dispatcher artifacts, Phase 3) |
| PR-quality CI prompts | `.claude/skills/review/references/{role}.md` | `.github/prompts/pr-quality-gate-{role}.md` | `build/scripts/generate_pr_quality_prompts.py` |
| Shared Python libs | `scripts/hook_utilities`, `scripts/github_core`, `scripts/ai_review_common` | `.claude/lib/{hook_utilities,github_core,ai_review_common}` (imports rewritten to relative) | `scripts/sync_plugin_lib.py` (SYNC_PAIRS at lines 27-31); `--check` is the CI dry-run |
| Self-host agent copies | the sources above | `.claude/agents/<name>.md`, `.github/agents/<name>.agent.md` | hand-synced, guarded by `build/scripts/validate_install_parity.py` |

Direction rule: generators read canonical, write mirrors. They NEVER write `.claude/`. That invariant is enforced in code: `build/scripts/build_all.py:962` ("REQ-003-010: enforce .claude/ no-write invariant"); any generator write under `.claude/` prints `REQ-003-010 VIOLATION` and exits 2. When a drift check goes red, the output shows a difference, not a direction. Always answer "which side is canonical?" from the table above before editing either side. An agent once "fixed" drift by editing the source to match the generated tree (2025-12-15 incident, commit reverted); the archaeology lives in `ai-agents-failure-archaeology`.

`src/claude/` semantic drift against templates is measured separately by `build/scripts/detect_agent_drift.py` (similarity floor, exit 1 on drift; `.github/workflows/agent-drift-detection.yml`).

### Phase 2: Load the load-bearing decisions

| Decision | ADR | Status (as of 2026-07-03) | Why it exists |
|---|---|---|---|
| Memory-first: retrieval precedes reasoning; Serena (`.serena/memories/`, 122 files) canonical, Forgetful supplementary | ADR-007 | Accepted (revised 2026-01-01) | Agents re-derive knowledge badly; retrieval is cheaper and auditable |
| HANDOFF.md read-only, distributed handoffs | ADR-014 | Accepted | Single-file write target caused merge-conflict storms |
| Two-source agent templates (shared templates plus hand-written `src/claude/`) | ADR-036 | Accepted | Claude prompts need harness-specific depth; 3 full sources would drift |
| Python-only new scripts, bash prohibited | ADR-042 | Accepted | One toolchain, testable, cross-platform |
| Skill-first over subagent dispatch | ADR-030 | doc's own header reads "Status: Critical Update - Changes Recommendation" (line 4); treated as binding by AGENTS.md Skill-First section | In-context skill plus direct MCP call is 5-20ms vs 100-200ms Task spawn overhead (ADR-030 line 31 comparison table) |
| Memory skill decomposition into tiers | ADR-063 | Accepted | Tier 1 semantic (Serena plus Forgetful search), Tier 2 episodic, Tier 3 causal |
| Hook failure policy: prevention-first, fail-closed-and-loud | ADR-066 | Proposed, but the position is the owner's canonical one after incident #2205 | Launcher fail-open hid a broken hook from every customer for 33 days |
| Plugin hook runtime-contract verification | ADR-071 | Accepted (six-agent adr-review) | Vendor docs were wrong by omission twice; contracts are tested, not assumed |
| Consolidated per-event hook dispatcher for Copilot CLI | ADR-068 | Proposed; implementation exists (`build/scripts/generate_dispatcher.py`) | Copilot ignores matchers and kills hooks at 2-3s; 40 shims per event blew the budget |
| JTBD plugin slicing, per-harness emission | ADR-072 | Proposed, five approval conditions unmet, "No code moves on this ADR alone" | Plugins are sliced by directory today, not by job-to-be-done |
| Context corpus is the product | ADR-069 | Proposed | Thesis only; do not cite as settled |
| LSP-first navigation enforcement | ADR-062 | Proposed; hooks are live anyway | Symbol queries beat grep on token cost |

Two meta-patterns bind these together:

**Name-based dispatch everywhere.** Nothing static-imports an agent, skill, command, or hook. Agents are invoked by `subagent_type` string, skills by frontmatter `name`, commands by filename, hooks by command-path strings inside `.claude/settings.json`, and the Copilot dispatcher resolves shims from `hooks.json` order ("the authoritative registered set, NOT a directory listing", `generate_dispatcher.py` docstring). Consequence: "no caller found" does NOT mean dead code. Grep and LSP reference searches will show zero callers for live, load-bearing files. Before deleting anything, check string references (settings.json, hooks.json, frontmatter, prose) and run `orphan-ref-validator`; for history, use `chestertons-fence`.

**Verification-based governance.** Every rule that matters is paired with a gate that produces an inspectable artifact: no-write invariant (exit 2 plus audit entry in `build/audit/GENERATION-AUDIT.md`), drift (`build_all.py --check`, `generate_agents.py --validate`), lib sync (`sync_plugin_lib.py --check`), plugin bumps (`build/scripts/validate_plugin_version_bump.py`), install parity (`validate_install_parity.py`), hook anchoring (`scripts/validation/validate_hook_anchoring.py`). `SESSION-PROTOCOL.md:30` states the doctrine and adds: labels like MANDATORY are insufficient; each requirement MUST have a verification mechanism. When you add a rule, add its gate; a rule without a gate is a wish. `ai-agents-change-control` covers how gates sequence into the change process.

### Phase 3: Understand the hook runtime and its failure policy

Registration is DUAL and partly hand-synced:

| Surface | File | Registered (as of 2026-07-03) |
|---|---|---|
| Claude Code direct | `.claude/settings.json` `hooks` key | 8 events, 23 matcher groups: PreToolUse, SessionStart, UserPromptSubmit, PostToolUse, Stop, SubagentStop, PreCompact, PermissionRequest |
| Plugin twin | `.claude/hooks/hooks.json` | 7 events, hand-ported; PreCompact is absent from the twin as of 2026-07-03 |
| Copilot CLI mirror | `src/copilot-cli/hooks/` plus its `hooks.json` | generated by `generate_hooks.py`; includes SessionEnd |

Failure policy is PER FAMILY, not global. Do not copy a policy across families:

| Family | Policy | Where stated |
|---|---|---|
| Push guards | fail-open on infrastructure errors, emitting `EVENT={...}` telemetry with `outcome="fail_open"`; bootstrap failure (missing plugin lib) exits 2, NOT fail-open | `.claude/hooks/PreToolUse/push_guard_base.py:20` and `:28` |
| LSP gate guards (ADR-062) | fail-open on bootstrap and state errors: never wedge a turn over navigation enforcement | `scripts/hook_utilities/lsp_gate_state.py` docstrings, `lsp_health.py` |
| Generated/released hook artifacts | prevention-first, fail-closed-and-loud: validate anchoring pre-release, and a novel runtime escape exits non-zero with actionable stderr | ADR-066 D1, ADR-071 |
| Copilot dispatcher | `gate` mode (PreToolUse) short-circuits on first non-zero exit, fail-closed; `observe` mode (PostToolUse, SessionStart, SessionEnd, UserPromptSubmit) runs every shim, always exits 0 | `build/scripts/generate_dispatcher.py` docstring |

The rationale for the split: guards that ASSERT AN INVARIANT on shipped artifacts must fail loud (a silent exit 0 disabled a hook for 33 days in #2205); guards that add ADVICE OR STEERING inside a session must not block the user's turn when their own machinery breaks. Older ADRs (008, 033, 035, 062) still carry blanket fail-open language; ADR-066 is the reconciliation and the binding direction even while its status field reads Proposed. SessionStart hooks cannot block regardless.

The dispatcher (ADR-068) exists because Copilot CLI ignores per-hook matchers, runs every registered entry on every tool call, and kills at 2-3s. One dispatcher per (plugin, event) replaces one process per shim; the docstring records ~75% spawn reduction (#2342). Harness behavior details (payload casing, plugin-root env vars, cwd) are `agent-harness-reference` territory; the flags and escape hatches (SKIP_LSP_GATE, LSP_DOWN, and the rest) are cataloged in `ai-agents-config-catalog`.

### Phase 4: Understand the memory architecture

- Canonical/supplementary split (ADR-007): `.serena/memories/` markdown files are the source of truth; Forgetful is a supplementary graph store. `scripts/memory_sync/sync_engine.py` mirrors Serena into Forgetful ("Serena-to-Forgetful synchronization ... to mirror Serena's canonical .serena/memories/ files").
- Tiers (ADR-063, Accepted): Tier 1 semantic search, Tier 2 episodic session replay, Tier 3 causal graph. Front doors are the `memory` and `memory-search` skills.
- Observation loop (issue #1345): the `reflect` skill and Stop hook detect corrections, observations land in Serena memories, and the skillbook agent graduates patterns. The retained `.claude/hooks/PreToolUse/invoke_correction_applier.py` and `invoke_topical_memory_injection.py` files are not registered in either Claude source manifest. Retrieve corrections and topical memories explicitly through the `memory` or `memory-search` skill. The absence is guarded by `tests/build_scripts/test_copilot_dispatcher_artifact.py::test_only_advisory_pretooluse_registrations_are_absent`.

Architectural consequence: memories are load-bearing runtime inputs, not documentation. Deleting or renaming a `.serena/memories/` file changes hook behavior in live sessions.

### Phase 5: Know the plugin and product surfaces

Three `plugin.json` trees, each independently versioned (values as of 2026-07-03):

| Tree | Plugin name | Version | Role |
|---|---|---|---|
| `.claude/.claude-plugin/plugin.json` | `project-toolkit` | 0.5.254 | the repo's own Claude Code surface, canonical for rules/skills/hooks/commands |
| `src/copilot-cli/.claude-plugin/plugin.json` | `project-toolkit` | 0.5.254 | generated Copilot CLI mirror of the same plugin |
| `src/claude/.claude-plugin/plugin.json` | `claude-agents` | 0.3.29 | hand-written Claude agent pack |

Any content change under one of those trees requires a strictly-greater semver bump of THAT tree's plugin.json (enforced by push hook plus `.github/workflows/validate-plugin-version-bump.yml`; motivation: stale plugin cache, PR #1942). Marketplaces: `.claude-plugin/marketplace.json` (lists `claude-agents` and `project-toolkit`) and `.github/plugin/marketplace.json`; parity checked by `build/scripts/check_plugin_manifest_parity.py`. The npm surface is `packages/ai-agents-cli` (`@rjmurillo/ai-agents`, 0.1.0, bin `ai-agents`). Release mechanics belong to `ai-agents-generation-and-release`.

### Phase 6: Check the invariants table before you change anything

| Invariant | Enforced by | Breaks what if violated |
|---|---|---|
| Generators never write `.claude/` | `build_all.py:962` REQ-003-010 check, exit 2 | Canonical tree gets silently overwritten by its own mirror; source of truth inverts |
| Generated trees match sources | `build_all.py --check`, `generate_agents.py --validate`, drift CI | Harness mirrors ship stale behavior; the two fix paths diverge |
| `.claude/lib/` matches `scripts/` packages | `sync_plugin_lib.py --check` | Plugin-distributed hooks import different code than the tested originals |
| Plugin content change implies version bump | push hook plus `validate-plugin-version-bump.yml` | Installed users run stale cached plugins (PR #1942) |
| Generated hooks anchor to repo root, never cwd | `scripts/validation/validate_hook_anchoring.py`, runtime-contract tests | #2205 class: hooks silently no-op in every customer install |
| HANDOFF.md is read-only | ADR-014, AGENTS.md Never list | Merge-conflict storm returns |
| No em/en dashes, block-style YAML arrays, no generated-file headers | `universal.md` MUST NOT 5/6, dash guards, bot reviewers | One review thread per violation, every PR |
| Hand-synced siblings stay identical | `validate_install_parity.py` | Self-hosted copies diverge from shipped ones |
| Retrieval precedes reasoning | ADR-007, session-protocol gates | Agents re-fight settled battles (see `ai-agents-failure-archaeology`) |

### Phase 7: Account for the known-weak points

State these plainly when working near them; do not design as if they were sound.

| Weak point | Evidence (as of 2026-07-03) | Consequence |
|---|---|---|
| `hooks.json` twin is hand-synced and already differs | `.claude/settings.json` registers 8 events incl. PreCompact; `.claude/hooks/hooks.json` registers 7, no PreCompact | Plugin installs may lack hooks the repo itself runs; verify intent before "fixing" either side |
| `src/claude/` manual dual-edit | `templates/README.md:131` | Shared-template edits silently skip the Claude surface unless you remember the second edit |
| Stale docs contradict reality | `CONTRIBUTING.md:155` said the removed PowerShell Generate-Agents command until PR #2871 repointed it to `python3 build/generate_agents.py`; zero `.ps1` files exist outside `.venv/` (ADR-042). `GENERATOR-FILES.md` lists `src/claude/` as a `generate_agents.py` output ("`src/claude/`, `src/copilot-cli/agents/`, `src/vs-code-agents/` (per platform YAML)"), but `generate_agents.py` contains no `src/claude` write and no claude platform YAML exists | Following docs verbatim fails; quote the canonical source when correcting (FM-9) |
| ruff is advisory in CI | `pytest.yml` comments around lines 107-119, issue #2194 style backlog | Lint debt accumulates invisibly; only syntax parsing blocks |
| Skill tests split by location | `pyproject.toml:41` `testpaths = ["tests"]`; `.claude/skills/<name>/tests/` NOT collected by default; `tests/skills/<name>/` is | Green CI does not prove skill tests ran; run them explicitly (`ai-agents-validation-and-qa`) |
| Proposed-ADR ambiguity | ADR-062/066/068/069/072 all read Proposed while their hooks, dispatcher, or doctrine are live | Status field is not a reliable "is this binding" signal; check enforcement, not status |
| EVENT telemetry consumer is thin | `push_guard_base.py` emits `EVENT=` lines; `guard-maturity` skill and `build/scripts/{aggregate_guard_intercepts,classify_guard_maturity}.py` consume, but no always-on pipeline is evident in-repo | Telemetry may be written and never read; verify before citing intercept ratios |
| Retro-cited SHAs unresolvable locally | full history is present (`git rev-list --count HEAD` = ~1471 as of 2026-07-03) but retro-cited short SHAs (`ddb76e0`, `01e76615a`) fail `git cat-file -t` | Archaeology still routes through retros and memories as primary sources, not git log |

## Anti-Patterns

- Editing a generated tree to fix drift. The next `build_all.py` run erases your work; the drift gate flags the diff, not the direction. Edit the canonical side per the Phase 1 table.
- Deleting a hook, skill, or script because "nothing references it". Dispatch is name-based; check string references and `orphan-ref-validator` first.
- Copying a failure policy across hook families. Push-guard fail-open reasoning does not transfer to released hook artifacts (ADR-066), and vice versa.
- Citing a Proposed ADR (069, 072) as settled architecture, or dismissing a live enforcement mechanism because its ADR reads Proposed (062, 066, 068).
- Treating `.serena/memories/` as inert docs. They are runtime inputs to correction-applier hooks.
- Adding a rule without a gate. Verification-based governance means prose without enforcement is dead on arrival (route new rules through `ai-agents-change-control`).
- Bumping the wrong plugin.json, or none. The bump belongs to the tree whose content changed, strictly greater.

## Verification

Before relying on or amending this contract:

- [ ] Ran `python3 build/scripts/build_all.py --check` and `python3 build/generate_agents.py --validate` from repo root; both exit 0 on a clean tree
- [ ] Confirmed the canonical side of any file you plan to edit against the Phase 1 table (and `GENERATOR-FILES.md`, minding its known `src/claude` row error)
- [ ] Confirmed event counts still match: `python3 -c "import json; d=json.load(open('.claude/settings.json'))['hooks']; print(len(d), sum(len(v) for v in d.values()))"` (expected 8 and 23 as of 2026-07-03)
- [ ] Checked the ADR status header of any decision you cite (statuses drift; content beats number, and ADR numbers have collided historically)
- [ ] If you touched `.claude/`, `src/claude/`, or `src/copilot-cli/`: bumped that tree's plugin.json strictly greater

## Provenance and Maintenance

Verified 2026-07-03 against the working tree. Volatile facts are date-stamped inline. Sources and re-verification commands:

| Claim | Source | Re-verify |
|---|---|---|
| Asymmetric seam, "No code moves on this ADR alone" | `.agents/architecture/ADR-072-jtbd-plugin-architecture.md` (Status, "the seam is asymmetric" section) | `grep -n "asymmetric" .agents/architecture/ADR-072-*.md` |
| Generator inventory, 7 generators | `build/scripts/build_all.py:426` GENERATORS; `.agents/governance/GENERATOR-FILES.md` | `grep -n -A8 "^GENERATORS" build/scripts/build_all.py` |
| REQ-003-010 no-write invariant | `build/scripts/build_all.py:962` | `grep -n "REQ-003-010" build/scripts/build_all.py` |
| src/claude manual sync | `templates/README.md:131`; ADR-036 Accepted | `grep -n "MANUAL" templates/README.md` |
| lib sync pairs | `scripts/sync_plugin_lib.py:27` SYNC_PAIRS | `grep -n -A4 "SYNC_PAIRS" scripts/sync_plugin_lib.py` |
| 8 events / 23 matcher groups; twin lacks PreCompact | `.claude/settings.json`, `.claude/hooks/hooks.json` | the Verification checkbox one-liner, plus `python3 -c "import json; print(list(json.load(open('.claude/hooks/hooks.json'))['hooks']))"` |
| Push-guard fail policy | `.claude/hooks/PreToolUse/push_guard_base.py:20,28` | `grep -n "fail-open" .claude/hooks/PreToolUse/push_guard_base.py` |
| Fail-closed reversal, #2205 rationale | `.agents/architecture/ADR-066-*.md`, ADR-071 (Accepted) | `grep -n -A2 "## Status" .agents/architecture/ADR-066*.md .agents/architecture/ADR-071*.md` |
| Dispatcher modes, ~75% spawn reduction | `build/scripts/generate_dispatcher.py` docstring | `head -20 build/scripts/generate_dispatcher.py` |
| Skill vs subagent latency 5-20ms vs 100-200ms | `.agents/architecture/ADR-030-skills-pattern-superiority.md:31` | `grep -n "100-200ms" .agents/architecture/ADR-030*.md` |
| Memory sync direction | `scripts/memory_sync/sync_engine.py` module docstring | `head -8 scripts/memory_sync/sync_engine.py` |
| Explicit correction and topical-memory retrieval | `memory` and `memory-search` skills; retained hook files are unregistered | `pytest -q tests/build_scripts/test_copilot_dispatcher_artifact.py::test_only_advisory_pretooluse_registrations_are_absent` |
| Plugin names/versions, marketplaces, npm CLI | the three `.claude-plugin/plugin.json` files, `.claude-plugin/marketplace.json`, `.github/plugin/marketplace.json`, `packages/ai-agents-cli/package.json` | `find . -name plugin.json -not -path "*/node_modules/*"` then read each |
| Stale CONTRIBUTING pwsh commands | `CONTRIBUTING.md:155`; no repo `.ps1` files | `grep -n "pwsh" CONTRIBUTING.md; find . -name "*.ps1" -not -path "./.venv/*"` |
| ruff advisory | `.github/workflows/pytest.yml` (comments near lines 107-119, issue #2194) | `grep -n -i "ruff" .github/workflows/pytest.yml` |
| testpaths exclude skill tests | `pyproject.toml:41` | `grep -n "testpaths" pyproject.toml` |
| Verification-based enforcement doctrine | `.agents/SESSION-PROTOCOL.md:30` | `grep -n "verification-based" .agents/SESSION-PROTOCOL.md` |
| Full history (~1471 commits) with unresolvable retro-cited SHAs | local clone state | `git rev-list --count HEAD; git cat-file -t ddb76e0` (expect "Not a valid object name") |

Maintenance rule: when any row above fails its re-verify command, fix THIS file in the same PR as the change that broke it, and label anything newly Proposed as Proposed. Sibling map: pipeline operation `ai-agents-generation-and-release`, triage `ai-agents-debugging-playbook`, harness facts `agent-harness-reference`, flags `ai-agents-config-catalog`, change process `ai-agents-change-control`, history `ai-agents-failure-archaeology`, evidence bar `ai-agents-validation-and-qa`.
