# Execution Plan: Model Assignment + Pipeline Unification

## Metadata

| Field | Value |
|-------|-------|
| **Status** | Abandoned |
| **Created** | 2026-04-26 |
| **Abandoned** | 2026-09-03 |
| **Owner** | rjmurillo |
| **Complexity** | High |
| **Successor** | Issue #5282, ADR-052 |

## Why this plan was abandoned

Recorded 2026-09-03. None of the 27 tasks below was executed. Three of the plan's
load-bearing premises no longer hold.

1. **The parent issue closed.** The plan rides inside issue #1774 ("arch: JTBD-based
   plugin architecture with per-harness emission"), stated in the first Decision Log
   row below. That issue is now closed, so M6-T3 ("close issue #1774 only if M5-T4
   merged") has no target and the plan has no parent to deliver against.
2. **The governing ADR was superseded.** M2-T5 and M6-T1 both build on ADR-036
   (two-source agent template architecture). ADR-036 now carries
   `status: superseded` and `superseded-by: ADR-052`, recorded 2026-08-25 via the
   six-agent `adr-review` debate at `.agents/critique/ADR-052-debate-log.md`. The
   successor work is tracked by issue #5282, which re-scopes the migration against
   six agent surfaces rather than the three this plan assumes.
3. **The scheduling constraint expired.** The Risk Register and M4-T1 both treat
   15 June 2026 as a hard deadline for retiring `claude-sonnet-4-20250514`
   callsites. That date has passed, so the batch ordering derived from it no longer
   means anything.

Two further premises drifted. The plan names `build/Generate-Agents.ps1` as the
generator, which the ADR-042 Python migration replaced with
`build/generate_agents.py`. And it lists ADR-052 as proposed, with "verify file
exists first" as a task, which is now settled.

Kept rather than deleted because the 27-task decomposition, the dependency graph,
and the four Decision Log rows are the reasoning that issue #5282 inherits. The
research basis is at `.agents/analysis/model-assignment-strategy-research.md`.

Do not resume this plan. Plan the successor work under issue #5282.

## Objectives

**M0: ADR Audit and Decision Gate** *(resized L, more than 2 days)*
- [ ] M0-T1: Read and annotate ADR-002, ADR-021, ADR-036, ADR-039 against seven principles
- [ ] M0-T2: Draft amend/supersede/implement matrix including proposed ADR-052 (verify file exists first)
- [ ] M0-T3: Answer Q1, Q2, Q5, Q6, Q7 from research doc; verify Flow A platform yamls against current Copilot CLI + VS Code docs; verify ADR-052 existence
- [ ] M0-T4: Comment on issue #1774 as DRAFT. Do not finalize until M0-T3 settled

**M1: Flow B Inventory and Triage**
- [ ] M1-T1: Enumerate Flow B files with versioned IDs (grep with exact exclusion flags, save raw with documented command)
- [ ] M1-T2: Enumerate `claude-sonnet-4-20250514` callsites separately with 1-line context
- [ ] M1-T3: Classify each file; build `.agents/analysis/flow-b-inventory.yaml` using schema: `file`, `versioned_ids[]`, `category` (docs/example/eval-baseline/load-bearing), `runtime_consumed` (bool), `classification_rationale`, `migration_decision` (alias/fence/delete/defer)

**M2: claude.yaml + Agent Beachhead**
- [ ] M2-T1: Draft `templates/platforms/claude.yaml`. Required fields: `platform: claude`, `outputDir: src/claude`, `fileExtension: .md`, `model_tiers` (alias or pin), fallback chains in comments; schema-compatible with existing yamls; file parses without error
- [ ] M2-T2: Extend `Generate-Agents.ps1` to emit `src/claude/*.md` from `templates/agents/*.shared.md` *(resized L, fence pattern introduces new code paths; Pester tests required)*
- [ ] M2-T3: Establish Claude-specific fence pattern in shared template (one reference agent)
- [ ] M2-T4: Diff generated `src/claude/` against hand-maintained baseline; classify divergences
- [ ] M2-T5: Amend ADR-036 or draft successor ADR

**M3: Extend Emission to Skills, Commands, Rules**
- [ ] M3-T1: Add `templates/skills/` with one reference migration (proof: CI gate catches a bad migration, not just visual review)
- [ ] M3-T2: Add `templates/commands/` with one reference migration
- [ ] M3-T3: Add `templates/rules/` with one reference migration (coordinate with #1769 owner before starting)
- [ ] M3-T4: Update pre-commit hook. Specify: which artifact types validated, failure output, exit codes
- [ ] M3-T5: Add CI validation. Specify: each platform validated, what "diff from generated" failure looks like, SHA-pinned actions

**M4: Migrate 72 Flow B Files** *(M5-T2 and M5-T3 must merge BEFORE M4-T1 starts)*
- [ ] M4-T1: Batch 1, docs and example category, except any `runtime_consumed: true` files (those move to Batch 2); `claude-sonnet-4-20250514` callsites first regardless of category (retirement hard deadline June 15 2026)
- [ ] M4-T2: Batch 2, load-bearing category plus any docs/example files with `runtime_consumed: true`
- [ ] M4-T3: Batch 3, eval-baseline category; each file must have explicit `migration_decision` in inventory before migrating

**M5: Lint Rule + CI Enforcement** *(M5-T2 and M5-T3 must precede M4-T1, not parallel)*
- [ ] M5-T1: Build `build/scripts/Validate-ModelIds.py` in warn-only mode. Allowlists: `templates/platforms/*.yaml` and `do-not-update` fences; pytest suite covers clean/violation/allowlist/fence cases
- [ ] M5-T2: Wire lint into pre-commit hook (warn-only). Must merge before M4-T1
- [ ] M5-T3: Add CI workflow (warn-only, annotated with flip marker). Must merge before M4-T1
- [ ] M5-T4: Flip to error mode. Guard: full repo scan confirms zero violations; CI green on main after M4-T3

**M6: Governance ADR + Operator Escape Hatch** *(draft M6-T1 during M3 for early adr-review; merge after M5-T4)*
- [ ] M6-T1: Draft successor ADR. Seven principles as decisions; per-platform yaml registry pattern documented; tier routing policy (7 opus/14 sonnet/1 haiku); cross-links to all superseded/amended ADRs; adr-review [PASS] required; can be proposed during M4/M5, merged after M5-T4
- [ ] M6-T2: Document `CLAUDE_CODE_SUBAGENT_MODEL` escape hatch in `templates/README.md`. Scope, limits (inherit-only), built-in shadow pattern, link to `claude.yaml` fallback chain; no versioned IDs in examples
- [ ] M6-T3: Close issue #1774 only if M5-T4 merged and CI green; otherwise transition with explicit successor scope for Cursor/Codex CLI emission

**M6-T4 (added by critic): Degradation contract audit**
- [ ] M6-T4: Audit all 7 Opus-tier agents for Sonnet fallback declaration; audit 14 Sonnet-tier agents for Haiku acceptability; file issues or add frontmatter fallback field for any missing contracts

## Dependency Graph

```
M0-T1+T2 (parallel) ──► M0-T3 ──► M0-T4 (DRAFT until M0-T3 done)
M1-T1+T2 (parallel) ──► M1-T3

M0-T3 ──► M2-T1 ──► M2-T2 (L) ──► M2-T3 ──► M2-T4 ──► M2-T5
M1-T3 ──┘

                     M2-T2 ──► M3-T1 ┐
                               M3-T2 ├ (parallel) ──► M3-T4 + M3-T5 (parallel)
                               M3-T3 ┘ (coordinate #1769 before start)

M1-T3 ──► M5-T1 ──► M5-T2 ──► M4-T1 (GATE: M5-T2+T3 must merge first)
                  └──► M5-T3 ──┘
M4-T1 ──► M4-T2 ──► M4-T3 ──► M5-T4 (GUARD: zero violations confirmed)

M0-T2 + M2-T5 ──► M6-T1 (draft early during M3, merge after M5-T4)
M0-T3 ──────────► M6-T2 (parallel with M6-T1)
M6-T1 + M6-T2 ──► M6-T3 (close only if M5-T4 merged + CI green)
                   M6-T4 (degradation contract audit, parallel with M6-T3)

Critical path: M0 (L) ──► M2 (M2-T1 + M2-T2 L) ──► M3 ──► [M5-T1→T2→T3 gate] ──► M4 ──► M5-T4 ──► M6
```

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-04-26 | Model strategy rides inside #1774 unification, not parallel | Unification provides the indirection layer model strategy needs; building it separately would duplicate the platform yaml mechanism | Separate model-strategy-only PR without unification |
| 2026-04-26 | Flow B defaults to alias-only (Option A) pending M1 eval-baseline count | Zero plumbing cost; Claude Code native alias resolution handles current use cases | Option B: build-step pin-capable yaml (costs 3-5 days; re-evaluate if M1 finds >5 eval-baseline files) |
| 2026-04-26 | No raw versioned IDs in source files (lint-enforced) | Seven principles from research doc; Anthropic model retirements break workflows silently | Soft guideline without enforcement |
| 2026-04-26 | Cursor/Codex CLI emission deferred to v0.5.0 | Scope control; issue #1774 explicitly defers non-Claude/Copilot platforms | Include Cursor in this milestone |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-04-26 | Created plan. Research doc at `.agents/analysis/model-assignment-strategy-research.md`. Milestones M0-M6, 27 atomic tasks defined via milestone-planner + task-decomposer. Pre-mortem (analyst) + critic validation complete. Plan revised with 3 top changes: (1) Flow A yaml verification added to M0-T3, (2) `flow-b-inventory.yaml` schema fields defined in M1-T3, (3) M5-T2/T3 dependency on M4 clarified as prerequisites. Additional: M0 and M2-T2 resized L; M6-T4 degradation contract audit added; `claude-sonnet-4-20250514` June 15 hard deadline recorded. | rjmurillo[bot] |
| 2026-09-03 | Abandoned. Parent issue #1774 closed, ADR-036 superseded by ADR-052, and the June 15 2026 deadline passed. Zero of 27 tasks executed. Successor work tracked by issue #5282. | rjmurillo[bot] |

## Blockers

- Q2 (alias vs build-step for Flow B) is provisionally answered as alias-only but should be re-evaluated after M1-T3 reveals eval-baseline count. If >5 eval-baseline files found, M2 scope may expand.
- Issue #1769 (monolith `.agents/*.md` extraction) overlaps with `templates/rules/` in M3. Coordinate with #1769 before M3 starts to avoid merge conflict.
- `claude-sonnet-4-20250514` snapshot has an announced retirement window. Prioritize in M4-T1 regardless of category.

## Risk Register

| Risk | P-level | Likelihood | Impact | Mitigation |
|------|---------|-----------|--------|------------|
| **#1774 stalls permanently** | P0 | Med | High | Decouple `claude.yaml` from #1774 approval; create file, link issue, do not block on issue owner |
| **M0-T3 reveals ADR conflict that invalidates architecture** | P0 | Med | High | Run M0-T1+T3 in first session; escalate conflict immediately; do not let M2 start on contested architecture |
| Claude-specific sections too divergent to generate cleanly (M2-T2) | P1 | Med | High | Fence pattern; scope M2 down to non-agent files if divergence is large; M2-T4 diff review is the gate |
| `claude-sonnet-4-20250514` retires June 15 2026 before M4-T1 | P1 | High | High | Treat June 15 as hard deadline for M4-T1; legacy-snapshot callsites are first in batch regardless of category |
| #1769 lands in conflicting shape before M3-T3 | P1 | Med | Med | Coordinate labels and milestone with #1769 owner before M3-T3 starts |
| M1 eval-baseline count > 5 (flips Q2 decision to Option B) | P1 | Low | Med | If true, M2 scope expands to pin-capable yaml before M3; re-estimate at M1-T3 completion |
| ADR-052 does not exist | P1 | Med | Low | M0-T2 verifies existence first; if missing, adjust cross-links in M2-T5 and M6-T1 |
| `Generate-Agents.ps1` becomes monolith after M3 | P2 | Med | Med | Evaluate splitting into per-artifact-type modules after M2 review |
| Flow A platform yamls carry wrong model IDs today | P2 | Low | Med | M0-T3 verifies against current Copilot CLI + VS Code docs before any yaml is used as template |
| adr-review debate blocks M2-T5/M6-T1 merge | P2 | Med | Low | Draft M6-T1 early during M3; run adr-review in parallel with M4, not as a gate before M3 |

## Related

- Issue: #5282 (implement ADR-052 Claude-first template migration): successor
- Issue: #1774 (JTBD-based plugin architecture, per-harness emission): parent, closed
- Issue: #1072 (Epic v0.4.0 Framework Extraction): grandparent epic
- Issue: #1769 (extract monolith .agents/*.md into scoped rules): adjacent dependency
- Issue: #1620 (Stage 2 Copilot Infrastructure): adjacent dependency
- Research: `.agents/analysis/model-assignment-strategy-research.md`
- ADR: `.agents/architecture/ADR-036-two-source-agent-template-architecture.md` (superseded by ADR-052)
- ADR: `.agents/architecture/ADR-021-model-routing-strategy.md`
- PR: none. No task was executed.
