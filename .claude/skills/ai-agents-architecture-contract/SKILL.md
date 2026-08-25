---
name: ai-agents-architecture-contract
description: Load-bearing design decisions for this repo as a contract you check before changing anything. Covers the asymmetric generation seam, source-of-truth per tree, hook runtime failure policy, memory tiers, plugin surfaces, invariants, and known-weak points. Use when you say `which tree is canonical`, `architecture contract`, `why is this designed this way`. Do NOT use for operating the build pipeline (use `ai-agents-generation-and-release`) or CI triage (use `ai-agents-debugging-playbook`).
version: 1.0.0
license: MIT
---

# AI Agents Architecture Contract

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself. It intentionally references .agents/governance, .agents/architecture, .agents/architecture/README.md, .claude/lib, scripts/hook_utilities, scripts/github_core, scripts/ai_review_common, scripts/memory_sync, scripts/sync_plugin_lib.py, scripts/validation, build/generate_agents.py, build/scripts, build/scripts/generate_adr_index.py, templates/agents, and templates/platforms because its audience is repo contributors, not plugin consumers. Issue #2050. -->
This skill is the map of design decisions that hold this repository up: what is canonical, what is generated, which invariants are enforced by gates, and where the structure is honestly weak. Read it before any change that touches more than one tree, any hook, any plugin surface, or any generated file. The repo's governance runs on observable evidence, not trust: active requirements name evidence that exists independent of any committed session log, so almost every claim below is backed by a gate you can run. (PR #5135, 2026-08-18, retired the earlier "verification-based enforcement" wording in favor of this evidence-sink framing; SESSION-PROTOCOL.md, the doc that carried that wording, was later deleted along with the session skill cluster.)

## Triggers

- `which tree is canonical`
- `architecture contract`
- `why is this designed this way`
- `what invariant am I about to break`
- `where is the source of truth for this file`

## Process

### Phase 1: Locate the source of truth before touching any file

The generation seam is ASYMMETRIC. There is no single "templates in, everything out" pipeline. Two seams coexist (ADR-072, status Proposed, corrected this premise explicitly: "the seam is asymmetric"):

1. Agents: `templates/agents/*.shared.md` is canonical for the Copilot CLI and VS Code copies only; `src/copilot-cli/agents/` and `src/vs-code-agents/` are generated from it. `src/claude/*.md` is NOT: it is hand-written canonical (see the table row below).
2. Rules, skills, commands, hooks: `.claude/` itself is canonical (Claude Code consumes it directly); generators emit mirrors for other harnesses.

Source-of-truth table (verified against `.agents/governance/GENERATOR-FILES.md` and `build/scripts/build_all.py` GENERATORS list at line 481; 8 generators: agents, agent-catalog, adr-index, skills, commands, rules, lib, hooks):

| Artifact class | Canonical source (edit here) | Generated or mirrored output (never edit) | Mechanism |
|---|---|---|---|
| Agents (Copilot CLI, VS Code) | `templates/agents/*.shared.md` | `src/copilot-cli/agents/`, `src/vs-code-agents/` | `build/generate_agents.py` per `templates/platforms/*.yaml` `outputDir` |
| Agents (Claude Code) | `src/claude/*.md` is itself canonical, hand-written | none; `.claude/agents/` is a hand-maintained sibling copy | MANUAL dual edit (ADR-036, Accepted); `templates/README.md:131`: "**Also edit**: `src/claude/{agent}.md` (MANUAL - not auto-synced!)" |
| Rules | `.claude/rules/*.md` | `.github/instructions/`, `src/copilot-cli/instructions/` | `build/scripts/generate_rules.py` |
| Skills | `.claude/skills/<name>/` | `src/copilot-cli/skills/<name>/` | `build/scripts/generate_skills.py` |
| Commands | `.claude/commands/<name>.md` | `src/copilot-cli/skills/<name>/SKILL.md` | `build/scripts/generate_commands.py` |
| Hooks | `.claude/hooks/` plus `.claude/settings.json` | `src/copilot-cli/hooks/` plus its `hooks.json` | `build/scripts/generate_hooks.py` (plus dispatcher artifacts, Phase 3) |
| PR-quality CI prompts | `.claude/skills/review/references/{role}.md` | `.github/prompts/pr-quality-gate-{role}.md` | `build/scripts/generate_pr_quality_prompts.py` |
| ADR current-state index | the ADR records under `.agents/architecture/` (lifecycle status, date, successor from frontmatter; title, decision summary, blocker from body prose) | `.agents/architecture/README.md` | `build/scripts/generate_adr_index.py` (issue #5198) |
| Shared Python libs | `scripts/hook_utilities`, `scripts/github_core`, `scripts/ai_review_common` | `.claude/lib/{hook_utilities,github_core,ai_review_common}` (imports rewritten to relative) | `scripts/sync_plugin_lib.py` (SYNC_PAIRS at lines 27-31); `--check` is the CI dry-run |
| Self-host agent copies | the sources above | `.claude/agents/<name>.md`, `.github/agents/<name>.agent.md` | hand-synced, guarded by `build/scripts/validate_install_parity.py` |

Direction rule: generators read canonical, write mirrors. They NEVER write `.claude/`. That invariant is enforced in code: `build/scripts/build_all.py:1171` ("REQ-003-010: enforce .claude/ no-write invariant"); any generator write under `.claude/` prints `REQ-003-010 VIOLATION` and exits 2. When a drift check goes red, the output shows a difference, not a direction. Always answer "which side is canonical?" from the table above before editing either side. An agent once "fixed" drift by editing the source to match the generated tree (2025-12-15 incident, commit reverted); the archaeology lives in `ai-agents-failure-archaeology`.

`build/scripts/detect_agent_drift.py` measures something else again, and NOT against templates: it scores `src/claude` against `src/vs-code-agents`, and `.claude/agents` against `.github/agents`, over an 18-section allowlist. It is a similarity floor (default 80), not an equality check, and it is a weekly audit rather than a merge gate: `.github/workflows/drift-detection.yml` triggers only on `schedule` (Mondays 09:00 UTC) and `workflow_dispatch`, and opens an issue on drift. The PR-time workflow `agent-drift-detection.yml` runs `generate_agents.py --validate` instead and never invokes this detector. Template bodies are never a comparison input, and for four agents the allowlist matches nothing so the score is hardcoded to 100.0 and the check cannot fail. See `.claude/rules/claude-agents.md` for the measured trip point and what its green does and does not prove.

### Phase 2: Load the load-bearing decisions

| Decision | ADR | Status (as of 2026-07-30) | Why it exists |
|---|---|---|---|
| Memory-first: retrieval precedes reasoning; Serena (`.serena/memories/`) canonical, Forgetful supplementary | ADR-007 | Accepted (revised 2026-01-01) | Agents re-derive knowledge badly; retrieval is cheaper and auditable |
| HANDOFF.md read-only, distributed handoffs | ADR-014 | Accepted | Single-file write target caused merge-conflict storms |
| Two-source agent templates (shared templates plus hand-written `src/claude/`) | ADR-036 | Accepted | Claude prompts need harness-specific depth; 3 full sources would drift |
| Python-only new scripts, bash prohibited | ADR-042 | Accepted | One toolchain, testable, cross-platform |
| Skill-first over subagent dispatch | ADR-030 | doc's own header reads "Status: Critical Update - Changes Recommendation" (line 4); treated as binding by AGENTS.md Skill-First section | In-context skill plus direct MCP call is 5-20ms vs 100-200ms Task spawn overhead (ADR-030 line 31 comparison table) |
| Memory skill decomposition into tiers | ADR-063, amended by ADR-089 | Accepted; ADR-089 proposed | Tier 1 semantic (Serena plus Forgetful search), Tier 2 episodic. ADR-063's Tier 3 causal graph was removed: nothing read it |
| Hook failure policy: prevention-first, fail-closed-and-loud | ADR-066 | Accepted (2026-07-19) | Launcher fail-open hid a broken hook from every customer for 33 days |
| Plugin hook runtime-contract verification | ADR-071 | Accepted (six-agent adr-review) | Vendor docs were wrong by omission twice; contracts are tested, not assumed |
| Consolidated per-event hook dispatcher for Copilot CLI | ADR-068 | Accepted (2026-07-19); rationale narrowed after the 2026-07-22 hook purge | Historical matcher and timeout behavior made one process per shim unsafe; #3218 closed after confirming the generation machinery remains live |
| JTBD plugin slicing, per-harness emission | ADR-072 | Proposed, five approval conditions unmet, "No code moves on this ADR alone" | Plugins are sliced by directory today, not by job-to-be-done |
| Context corpus is the product | ADR-069 | Proposed | Thesis only; do not cite as settled |
| LSP-first navigation (static steering) | ADR-062 | Amended 2026-07; runtime enforcement retired (#3216) | Symbol queries beat grep on token cost |

Two meta-patterns bind these together:

**Name-based dispatch everywhere.** Nothing static-imports an agent, skill, command, or hook. Agents are invoked by `subagent_type` string, skills by frontmatter `name`, commands by filename, hooks by command-path strings inside `.claude/settings.json`, and the Copilot dispatcher resolves shims from `hooks.json` order ("the authoritative registered set, NOT a directory listing", `generate_dispatcher.py` docstring). Consequence: "no caller found" does NOT mean dead code. Grep and LSP reference searches will show zero callers for live, load-bearing files. Before deleting anything, check string references (settings.json, hooks.json, frontmatter, prose) and run `orphan-ref-validator`; for history, use `chestertons-fence`.

**Verification-based governance.** Every rule that matters is paired with a gate that produces an inspectable artifact: no-write invariant (exit 2 plus audit entry in the generation audit log), drift (`build_all.py --check`, `generate_agents.py --validate`), lib sync (`sync_plugin_lib.py --check`), plugin version-field prohibition (`build/scripts/validate_plugin_version_bump.py`), install parity (`validate_install_parity.py`), hook anchoring (`scripts/validation/validate_hook_anchoring.py`). The current doctrine: labels such as "MANDATORY" are not enforcement. Each active requirement must name evidence that exists without requiring a committed session log. When you add a rule, add its gate; a rule without a gate is a wish. `ai-agents-change-control` covers how gates sequence into the change process.

### Phase 3: Understand the hook runtime and its failure policy

Registration is split by consumer. These source files are intentionally not
parity twins:

| Surface | File | Registered (re-verified 2026-08-19) |
|---|---|---|
| Claude Code direct | `.claude/settings.json` `hooks` key | 4 events, 6 groups |
| Vendored plugin source | `.claude/hooks/hooks.json` | 0 events, 0 groups |
| Copilot CLI mirror | `src/copilot-cli/hooks/` plus its `hooks.json` | 0 events, 0 registrations |

Failure policy is PER FAMILY, not global. Do not copy a policy across families:

| Family | Policy | Where stated |
|---|---|---|
| Local Claude hooks | Follow each event contract. SessionStart cannot block; Stop may return a block decision | `.claude/settings.json`; `agent-harness-reference` |
| Generated/released hook artifacts | Prevention-first and loud: validate anchoring before release, then surface escaped launcher failures | ADR-066 D1, ADR-071 |
| Copilot dispatcher | Retired (ADR-097): all three PreToolUse shims (`invoke_require_subagent_model`, `invoke_serena_memory_scope_guard` issue #5061, `invoke_serena_worktree_scope_guard` issue #4917) are deleted, and with them the generated `gate` dispatcher itself. `src/copilot-cli/hooks/hooks.json` carries `"hooks": {}`; no `_dispatch.py` ships. The generator still owns the policy for a future re-add | Deleted manifests; `build/scripts/generate_dispatcher.py` |

Why the split fails loud on shipped artifacts (the #2205 33-day silent-no-op incident), why older ADRs (ADR-008, ADR-033, ADR-035) still read fail-open, and why one dispatcher per event persists (ADR-068, Copilot CLI version history) are in `references/hook-runtime.md`. SessionStart hooks cannot block regardless. Harness exit and timeout details are owned by `agent-harness-reference`.

### Phase 4: Understand the memory architecture

- Canonical/supplementary split (ADR-007): `.serena/memories/` markdown files are the source of truth; Forgetful is a supplementary graph store. `scripts/memory_sync/sync_engine.py` mirrors Serena into Forgetful ("Serena-to-Forgetful synchronization ... to mirror Serena's canonical .serena/memories/ files").
- Tiers (ADR-063, Accepted; amended by ADR-089, Proposed): Tier 1 semantic search, Tier 2 episodic session replay. The Tier 3 causal graph shipped by ADR-063 was deleted because it was a derived cache with no reader. Front doors are the `memory` and `memory-search` skills.
- Observation loop (issue #1345): the `reflect` skill detects corrections, observations land in Serena memories, and the skillbook agent graduates patterns. The advisory correction-applier and topical-memory-injection PreToolUse hooks were deleted (issue #3184) after being deregistered from both Claude source manifests. Retrieve corrections and topical memories explicitly through the `memory` or `memory-search` skill. The absence is guarded by `tests/build_scripts/test_copilot_dispatcher_artifact.py::TestDispatcherArtifacts::test_retired_hooks_are_absent_and_keepers_are_plugin_only`.

Architectural consequence: memories are load-bearing runtime inputs, not documentation. Deleting or renaming a `.serena/memories/` file changes hook behavior in live sessions.

### Phase 5: Know the plugin and product surfaces

Three `plugin.json` trees ship, and none of them carries a version:

| Tree | Plugin name | Role |
|---|---|---|
| `.claude/.claude-plugin/plugin.json` | `project-toolkit` | the repo's own Claude Code surface, canonical for rules/skills/hooks/commands |
| `src/copilot-cli/.claude-plugin/plugin.json` | `project-toolkit` | generated Copilot CLI mirror of the same plugin |
| `src/claude/.claude-plugin/plugin.json` | `claude-agents` | hand-written Claude agent pack |

No manifest may carry a `version` field, and neither may a marketplace entry.
With the field absent, Claude Code resolves freshness from the git commit SHA,
which moves on every merge; with it present, freshness pins to the string until
someone hand-bumps it. Enforced by the push hook plus
`.github/workflows/validate-plugin-version-bump.yml` (ADR-092, which supersedes
ADR-079; issue #4080). Marketplaces: `.claude-plugin/marketplace.json` (lists
`claude-agents` and `project-toolkit`) and `.github/plugin/marketplace.json`;
parity checked by `build/scripts/check_plugin_manifest_parity.py`. The npm
surface is `packages/ai-agents-cli` (package `@rjmurillo/ai-agents`, bin
`ai-agents`; read its `package.json` for the current version). Release mechanics
belong to `ai-agents-generation-and-release`.

### Phase 6: Check the invariants table before you change anything

| Invariant | Enforced by | Breaks what if violated |
|---|---|---|
| Generators never write `.claude/` | `build_all.py:1171` REQ-003-010 check, exit 2 | Canonical tree gets silently overwritten by its own mirror; source of truth inverts |
| Generated trees match sources | `build_all.py --check`, `generate_agents.py --validate`, drift CI | Harness mirrors ship stale behavior; the two fix paths diverge |
| `.claude/lib/` matches `scripts/` packages | `sync_plugin_lib.py --check` | Plugin-distributed hooks import different code than the tested originals |
| No `version` field in any manifest or marketplace entry | push hook plus `validate-plugin-version-bump.yml` | Freshness pins to a hand-bumped string instead of the commit SHA, and the line conflicts across every concurrent plugin PR (ADR-092, issue #4080) |
| Generated hooks anchor to repo root, never cwd | `scripts/validation/validate_hook_anchoring.py`, runtime-contract tests | #2205 class: hooks silently no-op in every customer install |
| HANDOFF.md is read-only | ADR-014, AGENTS.md Never list | Merge-conflict storm returns |
| No em/en dashes, block-style YAML arrays, no generated-file headers | `universal.md` MUST NOT 5/6, dash guards, bot reviewers | One review thread per violation, every PR |
| Hand-synced siblings change together | `validate_install_parity.py` (co-change, one direction: a solo `src/claude/` edit is exempt) | Self-hosted copies diverge from shipped ones |
| Retrieval precedes reasoning | ADR-007, session-protocol gates | Agents re-fight settled battles (see `ai-agents-failure-archaeology`) |

### Phase 7: Account for the known-weak points

State these plainly when working near them; do not design as if they were sound. The dated evidence and consequence for each are in `references/weak-points.md`.

- **Hook sources serve different consumers**: `.claude/settings.json` has 4 events and 6 groups, `.claude/hooks/hooks.json` has 0 events and 0 groups; do not force parity; verify repository-only vs vendored before editing either source. ADR-097 retired every tool-call hook, so the vendored surface ships no hooks at all and the generated Copilot tree carries no dispatcher.
- **`src/claude/` manual dual-edit**: shared-template edits silently skip the Claude surface unless you make the second edit.
- **Stale docs contradict reality**: following docs verbatim fails; quote the canonical source when correcting (FM-9).
- **Ruff debt is ratcheted, not eliminated**: changed-file and whole-tree count gates block regressions, but existing lint debt remains.
- **Skill tests split by location**: green CI does not prove skill tests ran; run them explicitly (`ai-agents-validation-and-qa`).
- **Proposed-ADR ambiguity**: the status field is not a reliable is-this-binding signal; check enforcement, not status.
- **EVENT telemetry pipeline fully retired (resolved)**: the emitter (`push_guard_base.py`), every guard built on it, and the classifier skill that consumed its output were all deleted under ADR-084 (issue #5154); no live source, no live consumer.
- **Retro-cited SHAs are clone-ref dependent and off `main`**: verify ancestry, then route archaeology through retros and memories rather than relying on `git log`.

## Anti-Patterns

- Editing a generated tree to fix drift. The next `build_all.py` run erases your work; the drift gate flags the diff, not the direction. Edit the canonical side per the Phase 1 table.
- Deleting a hook, skill, or script because "nothing references it". Dispatch is name-based; check string references and `orphan-ref-validator` first.
- Copying a failure policy across hook families. Push-guard fail-open reasoning does not transfer to released hook artifacts (ADR-066), and vice versa.
- Citing a Proposed ADR (069, 072) as settled architecture, or dismissing a live enforcement mechanism because an older ADR status is stale.
- Treating `.serena/memories/` as inert docs. The advisory correction-applier and topical-memory-injection hooks were deleted (issue #3184; see the Phase 4 observation-loop entry above); they were never active runtime inputs. Explicit retrieval through the `memory` or `memory-search` skill is what makes memories load-bearing, not an automatic hook.
- Adding a rule without a gate. Verification-based governance means prose without enforcement is dead on arrival (route new rules through `ai-agents-change-control`).
- Adding a `version` back to a plugin.json or marketplace entry. ADR-092 deleted it; the gate fails on its presence.

## Verification

Before relying on or amending this contract:

- [ ] Ran `uv run python build/scripts/build_all.py --check` and `uv run python build/generate_agents.py --validate` from repo root; both exit 0 on a clean tree
- [ ] Confirmed the canonical side of any file you plan to edit against the Phase 1 table (and `GENERATOR-FILES.md`, minding its known `src/claude` row error)
- [ ] Confirmed event counts still match: local settings print `4 6`, vendored source prints `0 0`, and generated Copilot config prints `0 0`
- [ ] Checked the ADR status header of any decision you cite (statuses drift; content beats number, and ADR numbers have collided historically)
- [ ] If you touched `.claude/`, `src/claude/`, or `src/copilot-cli/`: left the manifests version-free (`python3 build/scripts/validate_plugin_version_bump.py` exits 0)

## Provenance and Maintenance

Authored 2026-07-03, facts re-verified against the working tree on 2026-08-19. Volatile facts are date-stamped inline. The full per-claim source and re-verify command index is in `references/provenance.md`; consult it when editing or auditing this skill.

Maintenance rule: when any row in `references/provenance.md` fails its re-verify command, fix this skill (SKILL.md and the affected reference) in the same PR as the change that broke it, and label anything newly Proposed as Proposed. Sibling map: pipeline operation `ai-agents-generation-and-release`, triage `ai-agents-debugging-playbook`, harness facts `agent-harness-reference`, flags `ai-agents-config-catalog`, change process `ai-agents-change-control`, history `ai-agents-failure-archaeology`, evidence bar `ai-agents-validation-and-qa`.
