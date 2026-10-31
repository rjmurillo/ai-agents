---
name: ai-agents-architecture-contract
description: Load-bearing design decisions for this repo as a contract you check before changing anything. Covers the asymmetric generation seam, source-of-truth per tree, hook runtime failure policy, memory tiers, plugin surfaces, invariants, and known-weak points. Use when you say `which tree is canonical`, `architecture contract`, `why is this designed this way`. Do NOT use for operating the build pipeline (use `ai-agents-generation-and-release`) or CI triage (use `ai-agents-debugging-playbook`).
version: 1.0.0
license: MIT
metadata:
  distribution: repo-local
  routing:
    role: conditional-adjunct
    invoker: ai-agents-generation-and-release
    trigger: ai-agents-generation-and-release points here to explain why the generation seam is shaped this way
    user-facing: false
---

# AI Agents Architecture Contract

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths because its audience is repo contributors, not plugin consumers. Declared paths: .claude/lib, build/generate_agents.py, build/scripts/build_all.py, build/scripts/check_plugin_manifest_parity.py, build/scripts/detect_agent_drift.py, build/scripts/generate_dispatcher.py, build/scripts/validate_plugin_version_bump.py, scripts/validation/validate_hook_anchoring.py, templates/agents -->
This skill is the map of design decisions that hold this repository up: what is canonical, what is generated, which invariants are enforced by gates, and where the structure is honestly weak. Read it before any change that touches more than one tree, any hook, any plugin surface, or any generated file. The repo's governance runs on observable evidence, not trust: active requirements name evidence that exists independent of any committed session log, so almost every claim below is backed by a gate you can run.

## Triggers

- `which tree is canonical`
- `architecture contract`
- `why is this designed this way`
- `what invariant am I about to break`
- `where is the source of truth for this file`

## Process

### Phase 1: Locate the source of truth before touching any file

The generation seam is ASYMMETRIC. There is no single "templates in, everything out" pipeline. Two seams coexist (ADR-072 corrected this premise explicitly: "the seam is asymmetric"):

1. Agents: ADR-109 B1 made `templates/agents/` canonical for every agent tree. `<stem>.claude.md.tmpl` renders `src/claude/agents/<stem>.md`, `<stem>.copilot.md.tmpl` renders `src/copilot-cli/agents/<stem>.md`, which `.github/agents/` links to, and `<stem>.shared.md` renders `src/vs-code-agents/` and feeds `docs/agent-catalog.md`. `.claude/agents/` links to `src/claude/agents/` (ADR-119, status proposed 2026-10-17, `implemented: true`: the symlinks exist, the decision is not yet accepted) (see the table row below).
2. Rules, skills, hooks: ADR-109 B2 to B4 made `templates/rules/`, `templates/skills/`, and `templates/hooks/` canonical for the Claude tree. `rule_templates.py`, `skill_templates.py`, and `hook_templates.py` render into `src/claude/`, and binplace copies hooks and settings into `.claude/` and links the rest (ADR-119, proposed). A shipped skill's other files are hand-maintained under `src/claude/skills/<name>/`. Generators emit other harnesses' mirrors. There is no commands class: ADR-064 converted every command into a skill and deleted the commands-to-skills bridge, so skills are the single user-invocable surface and `check_commands_retired.py` blocks a command coming back.

The source-of-truth table (artifact class, canonical source, generated output, mechanism) is in `references/source-of-truth.md`. For one path, run the `generator-path` instrument (see Instruments); it prints role, class, canonical source, plugin tree, install tree, and the regenerate command from the binplace rows. It does not cover paths no binplace row names, such as `build/`.

Direction rule: generators read canonical, write mirrors. Outside the binplace step, they never write `.claude/` (binplace rows and ADR-108 template-owned skill files are allowlisted). That invariant is enforced in code: `assert_no_claude_writes` in `build/scripts/build_all.py`, applied under the comment "REQ-003-010: enforce .claude/ no-write invariant" (the `guard-lines` instrument prints current line numbers); any generator write under `.claude/` prints `REQ-003-010 VIOLATION` and exits 2. ADR-108 carves out the template-owned skill files under `.claude/skills/`, passed to the guard as an allowlist; binplace is the other writer. When a drift check goes red, the output shows a difference, not a direction. Always answer "which side is canonical?" from the table or the `generator-path` instrument before editing either side. An agent once "fixed" drift by editing the source to match the generated tree (2025-12-15 incident, commit reverted); the archaeology lives in `ai-agents-failure-archaeology`.

`build/scripts/detect_agent_drift.py` is not a template-drift check: it is a weekly similarity audit between agent trees and can pass while a tree is wrong. It scores `src/claude` against `src/vs-code-agents`, and `.claude/agents` against `.github/agents`, NOT against templates. The measured trip point and the 18-section allowlist are in `references/drift-detector.md`.

### Phase 2: Load the load-bearing decisions

The decision table (decision, record, note, why) is in `references/adr-decisions.md`. Read ADR status from the frontmatter with the `adr-status` instrument; it prints status, superseded-by, and implemented for every ADR this skill cites. These supersessions change what is binding:

- Memory: ADR-007 is superseded by ADR-106 (Serena-Only Memory Architecture). Cite ADR-106.
- Agent templates: ADR-036 is superseded by ADR-052, which ADR-109 superseded. Cite ADR-109.
- Hooks: ADR-097 retired every tool-call hook. ADR-066, ADR-068, and ADR-071 still own the policy and dispatcher rationale for a future re-add.
- Proposed records: ADR-069, ADR-089, and ADR-119 are proposed. ADR-072 is accepted with `implemented: false`, so accepting it moved no code.
- ADR-030 is rejected. The skill-first rule lives in `SKILL-CREATION-CRITERIA.md`.

The command does not say whether a mechanism is still enforced. Check the gate, not the status.

Two meta-patterns bind these together:

**Name-based dispatch everywhere.** Nothing static-imports an agent, skill, command, or hook. Agents are invoked by `subagent_type` string, skills by frontmatter `name`, commands by filename, hooks by command-path strings inside `.claude/settings.json`, and the Copilot dispatcher resolves shims from `hooks.json` order ("the authoritative registered set, NOT a directory listing", `generate_dispatcher.py` docstring). Consequence: "no caller found" does NOT mean dead code. Grep and LSP reference searches will show zero callers for live, load-bearing files. Before deleting anything, check string references (settings.json, hooks.json, frontmatter, prose) and run `orphan-ref-validator`; for history, use `chestertons-fence`.

**Verification-based governance.** Every rule that matters is paired with a gate that produces an inspectable artifact: no-write invariant (exit 2 plus audit entry in the generation audit log), drift (`build_all.py --check`, `generate_agents.py --validate`; the lib trees are covered by the same `build_all.py --check`, ADR-109 B5), plugin version-field prohibition (`build/scripts/validate_plugin_version_bump.py`), install parity (`validate_install_parity.py`), hook anchoring (`scripts/validation/validate_hook_anchoring.py`). The current doctrine: labels such as "MANDATORY" are not enforcement. Each active requirement must name evidence that exists without requiring a committed session log. When you add a rule, add its gate; a rule without a gate is a wish. `ai-agents-change-control` covers how gates sequence into the change process.

### Phase 3: Understand the hook runtime and its failure policy

Registration is split by consumer. These source files are intentionally not
parity twins:

| Surface | File | Registered (re-verified 2026-10-31) |
|---|---|---|
| Claude Code direct | `.claude/settings.json` `hooks` key | 5 events, 8 groups |
| Vendored plugin source | `.claude/hooks/hooks.json` | 0 events, 0 groups |
| Copilot CLI mirror | `src/copilot-cli/hooks/` plus its `hooks.json` | 0 events, 0 registrations |

Run the `hook-counts` instrument for the events and registrations in each file. It counts registrations only; it does not say whether a hook is repository-only or vendored.

Failure policy is PER FAMILY, not global. Do not copy a policy across families:

| Family | Policy | Where stated |
|---|---|---|
| Local Claude hooks | Follow each event contract. SessionStart cannot block; Stop may return a block decision | `.claude/settings.json`; `agent-harness-reference` |
| Generated/released hook artifacts | Prevention-first and loud: validate anchoring before release, then surface escaped launcher failures | ADR-066 D1, ADR-071 |
| Copilot dispatcher | Retired (ADR-097): all three PreToolUse shims (`invoke_require_subagent_model`, `invoke_serena_memory_scope_guard`, `invoke_serena_worktree_scope_guard`) are deleted, and with them the generated `gate` dispatcher itself. `src/copilot-cli/hooks/hooks.json` carries `"hooks": {}`; no `_dispatch.py` ships. The generator still owns the policy for a future re-add | Deleted manifests; `build/scripts/generate_dispatcher.py` |

Why the split fails loud on shipped artifacts (the 33-day silent-no-op incident), why older ADRs (ADR-008, ADR-033, ADR-035) still read fail-open, and why one dispatcher per event persists (ADR-068, Copilot CLI version history) are in `references/hook-runtime.md`. SessionStart hooks cannot block regardless. Harness exit and timeout details are owned by `agent-harness-reference`.

### Phase 4: Understand the memory architecture

- Single store (ADR-106, which superseded ADR-007; a later change deleted the supplementary store): `.serena/memories/` markdown files are the source of truth and the only memory backend. The supplementary graph store and the sync engine that mirrored Serena into it are deleted; nothing replaced them, so there is no second store to reconcile and no sync direction to know.
- Tiers (ADR-063, amended by ADR-089, which is proposed): Tier 1 semantic search, Tier 2 episodic session replay. The Tier 3 causal graph shipped by ADR-063 was deleted because it was a derived cache with no reader. Front doors are the `memory` and `memory-search` skills.
- Observation loop: the `reflect` skill detects corrections, observations land in Serena memories, and the skillbook agent graduates patterns. The advisory correction-applier and topical-memory-injection PreToolUse hooks were deleted after being deregistered from both Claude source manifests. Retrieve corrections and topical memories explicitly through the `memory` or `memory-search` skill. No test guards the absence; the `hook-counts` instrument shows no registered tool-call hook.

Architectural consequence: memories are load-bearing runtime inputs, not documentation. Deleting or renaming a `.serena/memories/` file changes hook behavior in live sessions.

### Phase 5: Know the plugin and product surfaces

Two Claude-format `plugin.json` manifests ship (src/claude, src/copilot-cli), and neither carries a version (ADR-109 B6
retired the third, `.claude/.claude-plugin/plugin.json`, which is absent, since `.claude/` is
now the binplaced dogfood copy, not a separately marketplace-listed root):

| Tree | Plugin name | Role |
|---|---|---|
| `src/claude/.claude-plugin/plugin.json` | `project-toolkit` | canonical Claude Code manifest, compiled from templates; the sole Claude Code plugin root the marketplace lists |
| `src/copilot-cli/.claude-plugin/plugin.json` | `project-toolkit` | generated Copilot CLI mirror of the same plugin |

Other hosts ship their own manifests, outside this contract: `src/codex/plugin.json`, `src/cursor/.cursor-plugin/plugin.json`, and `src/hermes/project-toolkit-delivery/plugin.json` plus `src/hermes/project-toolkit-knowledge/plugin.json`.

No manifest may carry a `version` field, and neither may a marketplace entry.
With the field absent, Claude Code resolves freshness from the git commit SHA,
which moves on every merge; with it present, freshness pins to the string until
someone hand-bumps it. Enforced by the push hook plus
`.github/workflows/validate-plugin-version-bump.yml` (ADR-092, which superseded
ADR-091, which superseded ADR-079). Marketplaces: `.claude-plugin/marketplace.json` (lists
one Claude-side plugin, `project-toolkit`, since ADR-109 B6 retired the
`claude-agents` entry) and `.github/plugin/marketplace.json`;
parity checked by `build/scripts/check_plugin_manifest_parity.py`. The npm
surface is `packages/ai-agents-cli` (package `@rjmurillo/ai-agents`, bin
`ai-agents`; read its `package.json` for the current version). Release mechanics
belong to `ai-agents-generation-and-release`. Run the `version-gate` instrument to check for a version field; it exits 1 on a hit.

### Phase 6: Check the invariants table before you change anything

| Invariant | Enforced by | Breaks what if violated |
|---|---|---|
| Generators never write `.claude/` (except the ADR-108 template-owned skill files) | `assert_no_claude_writes` in `build_all.py` (`guard-lines` instrument), exit 2 | Canonical tree gets silently overwritten by its own mirror; source of truth inverts |
| Generated trees match sources | `build_all.py --check`, `generate_agents.py --validate`, drift CI | Harness mirrors ship stale behavior; the two fix paths diverge |
| `.claude/lib/` matches `scripts/` packages | `build_all.py --check` | Plugin-distributed hooks import different code than the tested originals |
| No `version` field in any manifest or marketplace entry | push hook plus `validate-plugin-version-bump.yml` | Freshness pins to a hand-bumped string instead of the commit SHA, and the line conflicts across every concurrent plugin PR (ADR-092) |
| Generated hooks anchor to repo root, never cwd | `scripts/validation/validate_hook_anchoring.py`, runtime-contract tests | The 33-day silent-no-op class: hooks silently no-op in every customer install |
| No em/en dashes, block-style YAML arrays, no generated-file headers | `universal.md` MUST NOT 4/5, dash guards, bot reviewers | One review thread per violation, every PR |
| Hand-synced siblings change together | `validate_install_parity.py` (co-change, one direction: a solo `src/claude/` edit is exempt) | Self-hosted copies diverge from shipped ones |
| Retrieval precedes reasoning | ADR-106, memory gates | Agents re-fight settled battles (see `ai-agents-failure-archaeology`) |

### Phase 7: Account for the known-weak points

State these plainly when working near them; do not design as if they were sound. The dated evidence and consequence for each are in `references/weak-points.md`.

- **Hook sources serve different consumers**: the three sources are not parity twins. Do not force parity; verify repository-only vs vendored before editing either source. ADR-097 retired every tool-call hook, so the vendored surface ships no hooks and the generated Copilot tree carries no dispatcher. Counts on 2026-10-31: 5 events and 8 groups in settings, 0 events and 0 groups in the vendored source. Run the `hook-counts` instrument for current numbers.
- **Stale docs contradict reality**: following docs verbatim fails; quote the canonical source when correcting (FM-9).
- **Ruff debt is ratcheted, not eliminated**: changed-file and whole-tree count gates block regressions; existing debt remains.
- **Skill tests split by location**: green CI does not prove skill tests ran; run them explicitly (`ai-agents-validation-and-qa`).
- **Proposed-ADR ambiguity**: the status field is not a reliable is-this-binding signal (ADR-119 is proposed while its symlinks exist); check enforcement, not status.
- **EVENT telemetry pipeline retired**: no live source or consumer remains (ADR-084).
- **Retro-cited SHAs are clone-ref dependent and off `main`**: verify ancestry, then route archaeology through retros and memories.

## Anti-Patterns

- Editing a generated tree to fix drift. The next `build_all.py` run erases your work; the drift gate flags the diff, not the direction. Edit the canonical side per `references/source-of-truth.md`.
- Deleting a hook, skill, or script because "nothing references it". Dispatch is name-based; check string references and `orphan-ref-validator` first.
- Copying a failure policy across hook families. Push-guard fail-open reasoning does not transfer to released hook artifacts (ADR-066), and vice versa.
- Citing a proposed ADR (069, 089, 119) as settled architecture, or dismissing a live enforcement mechanism because an older ADR status is stale.
- Treating `.serena/memories/` as inert docs. Explicit retrieval through the `memory` or `memory-search` skill makes memories load-bearing; the auto-injection hooks were deleted.
- Adding a rule without a gate. Verification-based governance means prose without enforcement is dead on arrival (route new rules through `ai-agents-change-control`).
- Adding a `version` back to a plugin.json or marketplace entry. ADR-092 deleted it; the gate fails on its presence.

## Verification

Before relying on or amending this contract:

- [ ] Ran `uv run python build/scripts/build_all.py --check` and `uv run python build/generate_agents.py --validate` from repo root; both exit 0 on a clean tree
- [ ] Confirmed the canonical side of any file you plan to edit against `references/source-of-truth.md` (and `GENERATOR-FILES.md`, minding its known `src/claude` row error)
- [ ] Ran the `hook-counts` instrument and used its numbers, not a remembered count; on 2026-10-31 local settings print `5 8` and vendored source prints `0 0`
- [ ] Ran the `adr-status` instrument for any decision you cite (statuses drift; content beats number, and ADR numbers have collided historically)
- [ ] If you touched `.claude/`, `src/claude/`, or `src/copilot-cli/`: left the manifests version-free (the `version-gate` instrument exits 0)

## Scripts

Run any row with `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-architecture-contract/scripts/instruments.py" --repo . run <id>`. List the rows and check each exists with `... instruments.py --repo . list` (exit 1 when a row is missing). `generator-path` takes the path after `--`.

| Id | Answers |
|---|---|
| `adr-status` | Status, superseded-by, implemented flag of each cited ADR (`contract_probe.py adrs`) |
| `guard-lines` | Definition and call-site lines of `assert_no_claude_writes` (`contract_probe.py guard`) |
| `hook-counts` | Events and registrations per hook manifest |
| `generator-path` | Canonical source, plugin tree, install tree, regenerate command for one path |
| `version-gate` | Whether any manifest or marketplace entry carries a version |
| `claims` | Which cited paths and test node ids no longer exist |
| `drift-self-check` | Whether this skill drifted from `reverify.json` |

Exit codes for `instruments.py` and `contract_probe.py`: 0 ok, 1 when something is found (a missing instrument file, an absent ADR, no guard definition), 2 bad arguments or configuration, 3 the target failed to start or a file was unreadable. `run` passes the child exit code through. Each answer covers existence and counts only. Whether a mechanism still does its job stays a judgment call from the prose above.

## Provenance and Maintenance

Authored 2026-07-03, refreshed 2026-10-31 against 42e409325; facts re-verified against the working tree on 2026-10-31. `reverify.json` holds the machine-checkable claims; the drift command below runs them:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/skill-bootstrap/scripts/bootstrap_drift.py" check --repo . --skills-root .claude/skills --name ai-agents-architecture-contract --require
```

The per-claim source and re-verify command index is in `references/provenance.md`.

Maintenance rule: when a `reverify.json` check or a row in `references/provenance.md` fails, fix this skill (SKILL.md and the affected reference) in the same PR as the change that broke it, and label anything newly proposed as proposed. Sibling map: pipeline operation `ai-agents-generation-and-release`, triage `ai-agents-debugging-playbook`, harness facts `agent-harness-reference`, flags `ai-agents-config-catalog`, change process `ai-agents-change-control`, history `ai-agents-failure-archaeology`, evidence bar `ai-agents-validation-and-qa`.
