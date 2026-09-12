# Execution Plan: Template-first plugin distribution (ADR-109)

## Metadata

| Field | Value |
|-------|-------|
| **Status** | Active |
| **Created** | 2026-09-11 |
| **Owner** | rjmurillo |
| **Complexity** | High |
| **Spec** | REQ-026, DESIGN-025, TASK-031 (B1), TASK-032 (B2), TASK-033 (B3), TASK-034 (B4), TASK-035 (B5), TASK-036 (B6), ADR-109 |

## Objectives

- [x] B0: ADR-109 written, its own record; conditional amendment text staged for ADR-052, ADR-107, REQ-003, and the ADR index; done when ADR-109 is accepted and the staged text turns unconditional (ADR-109 section 5, section 6, Implementation Notes).
- [ ] B1: agents composed from paired `templates/agents/<stem>.claude.md.tmpl` / `<stem>.copilot.md.tmpl` templates and shared partials; `src/claude/agents/` rendered losslessly against today's output; `src/claude/`'s hand-maintained status retired; the binplace manifest introduced; `copilot-cli.yaml`'s agents `sourceDir` repointed; the lib ordering-hazard rule text updated to the target model (TASK-031).
- [ ] B2: rules move to `templates/rules/`; new compile module; manifest gains the `rules` row (TASK-032).
- [ ] B3: the remaining 93 skills templated in batches; skill_templates.py's render target moves to `src/claude/skills/`, giving skills the `src/claude/` plugin tree B1 does not deliver; the ADR-108 pilot-scope pin retired once the full 111-skill set matches `discover()` (TASK-033).
- [ ] B4: hooks and settings move to `templates/hooks/`; `src/claude/hooks/` and `src/claude/hooks.json` render for the first time; `.github/hooks/*.json` binplaced for the first time; the owner's ruleset decision on code-owner review recorded (TASK-034).
- [ ] B5: the lib mirror's two-hop chain collapses into one step inside `build_all.py`; `scripts/sync_plugin_lib.py` retired (TASK-035).
- [ ] B6: the marketplace switch; `claude-agents` retired, `project-toolkit` repointed to `./src/claude` (TASK-036).

## Milestones

### B0: the record itself

Exit criteria: ADR-109 accepted (lifecycle gate passes, `adr-review` round recorded if the owner requires one before B1 starts); the four staged amendment sites (ADR-052 Status note, ADR-107 property 1 and Related Decisions, REQ-003 D4/D9/REQ-003-010) turn from conditional to unconditional text; `.agents/architecture/README.md` lists ADR-109.

This milestone is the ADR itself, already written and referenced by every task below. Done: the owner accepted ADR-109 on 2026-09-11 (PR #5745), the frontmatter reads `accepted`, and the ADR-052, ADR-107, and REQ-003 amendments are unconditional.

| Task | Size | Done when |
|------|------|-----------|
| B0-T1 acceptance | S | ADR-109 `status: accepted`; `check_adr_lifecycle.py` passes |
| B0-T2 amendment sites | S | ADR-052 Status/frontmatter, ADR-107 property 1 and Related Decisions, REQ-003 D4/D9/REQ-003-010 all read the unconditional form |
| B0-T3 index | S | `.agents/architecture/README.md` regenerated; ADR-052's row moves from Accepted to Retired |

### B1: agents

Exit criteria: TASK-031 acceptance criteria hold; the 31 agents' first render is byte-identical to today's `src/claude/*.md` and today's `src/copilot-cli/agents/` (the losslessness fixture test passes); `build_all.py --check` exits 0 on a clean tree and 2 on a drifted `src/claude/agents/` file; the binplace manifest exists with two active rows (`agents`, `skills`, the latter delegating to `skill_templates.owned_targets` with `plugin_tree: null` until B3); `copilot-cli.yaml`'s agents `sourceDir` no longer names `.claude/` (a documentation-only repoint, since `generate_agents.py` never reads that field); `OWNED_PREFIXES` widened to include `.claude/agents/`; `Agent Template Drift` gate green.

| Task | Size | Done when |
|------|------|-----------|
| B1-T1 variant template pairs | L | `templates/agents/<stem>.claude.md.tmpl` and `<stem>.copilot.md.tmpl` populated for all 31 agents from today's `src/claude/` and `templates/agents/*.shared.md` content respectively; shared partials extracted only where the two members already agree |
| B1-T2 render target and compile module | M | `build/scripts/agent_templates.py` created; `build/generate_agents.py` renders `src/claude/agents/<name>.md`; `src-claude` pattern and drift-pair rewrites land in the same commit |
| B1-T3 binplace manifest and step | M | `templates/platforms/binplace.yaml` created; `build_all.py` gains `_binplace()`; `assert_no_claude_writes` reads the manifest for its allowlist; `copilot-cli.yaml`'s agents `sourceDir` repointed off `.claude/agents` |
| B1-T4 tests | M | Positive, negative, edge, symlink, and 31-agent losslessness cases for the agents compile target and the manifest loader |
| B1-T5 gates and governance | S | `Agent Template Drift` gate, registry test, CODEOWNERS, `GENERATOR-FILES.md`, `claude-agents.md` prose, `generated-artifacts.md`'s ordering-hazard section rewritten to the target model with the lib hazard flagged open until B5 |

### B2: rules

Exit criteria: TASK-032 acceptance criteria hold; `git diff --exit-code -- .claude/rules` exits 0 after a clean run; Copilot mirror (`.github/instructions/`, `src/copilot-cli/instructions/`) unaffected; `Rule Template Drift` gate green; manifest carries three active rows (`agents`, `skills`, `rules`).

| Task | Size | Done when |
|------|------|-----------|
| B2-T1 templates | S | `templates/rules/<name>.md` for all 30 rules, content unchanged from `.claude/rules/` |
| B2-T2 compile module | S | `build/scripts/rule_templates.py` reusing `skill_template_grammar`; `generate_rules.py` compiles before its existing mirror step |
| B2-T3 manifest and gate | S | `rules` row added; `Rule Template Drift` gate and registry entry |

### B3: remaining skills

Exit criteria: TASK-033 acceptance criteria hold; `discover()` on the real tree returns all 111 skill names; the pilot-scope pin test is deleted; every batch stayed within the file-count ceiling and kept `Skill Template Drift` green; `src/claude/skills/` renders for the first time and the manifest's `skills` row points its `plugin_tree` there instead of `null`; `OWNED_PREFIXES` widened to include `.claude/skills/`; the `prompts` manifest row lands for the twelve `pr-quality-gate-*.md` files.

| Task | Size | Done when |
|------|------|-----------|
| B3-T1 batching plan | S | Owner confirms batch count, size, and grouping (Open questions, REQ-026) before the first batch PR opens |
| B3-T2 render-target move | S | `skill_templates.compile_all` renders `src/claude/skills/<name>/SKILL.md`; binplace copies it into `.claude/skills/`; manifest's `skills` row `plugin_tree` set to `src/claude/skills`; `generate_skills.py`'s Copilot-mirror step repointed to read `src/claude/skills/` |
| B3-T3..T-n batches | M each | Each batch PR: at most ten files, `git diff --exit-code -- .claude/skills` clean, existing gate green |
| B3-T-final pin retirement | S | `tests/build_scripts/test_skill_templates_pilot_scope.py` deleted once the 93rd skill lands |
| B3-T-prompts | S | `prompts` manifest row added; `.github/prompts/pr-quality-gate-*.md` (12 files) binplaced from `.claude/skills/review/references` via `generate_pr_quality_prompts` |

### B4: hooks and settings

Exit criteria: TASK-034 acceptance criteria hold; `src/claude/hooks/` and `src/claude/hooks.json` render for the first time in this tree; `ls .github/hooks/*.json` lists at least one file; the extended runtime-contract test passes with its negative control; `Hook Template Drift` gate green; `OWNED_PREFIXES` widened to include `.claude/hooks/` and `.github/hooks/`; the owner's ruleset decision recorded in the PR.

| Task | Size | Done when |
|------|------|-----------|
| B4-T1 templates | S | `templates/hooks/` scoped to the class only: 13 executables, `hooks.json`, `dispatch_groups.json`, and `markdownlint-safe-config.yaml` (16), plus one settings template (17 files); the 7 doc files under `.claude/hooks/` stay hand-maintained, content of every templated file unchanged |
| B4-T2 compile module | M | `build/scripts/hook_templates.py`: byte copy plus JSON render into `src/claude/hooks/` and `src/claude/hooks.json`; `generate_hooks.py` and `generate_dispatcher.py` wired |
| B4-T3 binplace and manifest | S | `hooks` and `settings` rows added; `.github/hooks/*.json` written by the binplace step for the first time |
| B4-T4 runtime-contract test | M | Extends `test_generate_hooks_runtime_contract.py` with the cloud-agent case and its negative control |
| B4-T5 ruleset decision | S | PR body records whether `require_code_owner_review` becomes `true` before this task's writes land |

### B5: lib

Exit criteria: TASK-035 acceptance criteria hold; `scripts/sync_plugin_lib.py` deleted; the three packages copy correctly in one `build_all.py` run; `.claude/rules/generated-artifacts.md`'s ordering-hazard section rewritten; `check_plugin_lib_mirrors.py` rewired or retired with the decision recorded.

| Task | Size | Done when |
|------|------|-----------|
| B5-T1 absorb copy logic | M | `_build_lib` performs both hops in one run; `SYNC_PAIRS`, `SYNC_FILE_PAIRS`, `IMPORT_CONVERSIONS` moved verbatim |
| B5-T2 delete standalone script | S | `scripts/sync_plugin_lib.py` removed; no remaining caller invokes it directly |
| B5-T3 CI script and rule text | S | `check_plugin_lib_mirrors.py` rewired or deleted; `generated-artifacts.md`'s residual "hazard stays open until B5" note (added at B1) removed; CODEOWNERS entries added |

### B6: marketplace switch

Exit criteria: TASK-036 acceptance criteria hold; `claude-agents` entry gone; `project-toolkit` sourced at `./src/claude`; `.claude/.claude-plugin/plugin.json` deleted; rollback risk stated in the PR body.

| Task | Size | Done when |
|------|------|-----------|
| B6-T1 marketplace edits | S | Both manifest files edited, one file deleted, description text updated |
| B6-T2 rollback statement | S | PR body names the one-way-door window for an already-updated consumer |

## Sequencing

```text
B0 (accepted) --> B1 --> B2 --> B3 --> B4 --> B5 --> B6
```

B1 must land before B2 through B5, because each of those adds a row to the binplace manifest and a class-scoped allowance to `assert_no_claude_writes`'s allowlist, both introduced by B1. B2 through B4 do not depend on each other's internals (a rules-only change and a hooks-only change touch disjoint files), so their branches could be prepared in parallel worktrees, but ADR-109 section 7 fixes their merge order (rules, then remaining skills, then hooks and settings) and this plan does not deviate from that order without the owner's say. B5 depends on B4 only in the sense that it is sequenced after it, not in shared files; B5 could in principle land before B4 with no technical conflict, but the ADR's stated order is authoritative. B6 must be last: it is the one irreversible-in-practice step (a consumer who updates during the rollback window keeps the new source), so every other class must already be complete and self-contained under `src/claude/` before it runs.

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| B1's `src/claude/` layout move breaks a tool that still matches the flat path | High without care | High (silent drift in CI) | Rewrite `validate_install_parity.py` and `detect_agent_drift.py` in the same commit as the render-target change, per TASK-031 |
| B3's 93-skill batching stalls without an owner-confirmed plan | Medium | Medium (schedule) | B3-T1 blocks the first batch PR until the owner answers the open batching question |
| B4 writes executable hook configuration with no code-owner review requirement | Medium | High (a bad hook script reaches every plugin consumer) | PR body puts the ruleset decision to the owner explicitly; do not assume the current `require_code_owner_review: false` default is acceptable without asking |
| B5's import-rewrite regex diverges from `sync_plugin_lib.py`'s current output during the move | Low | High (broken imports in `.claude/lib/` or `src/copilot-cli/lib/`) | Diff pre- and post-migration output for all three packages before deleting the standalone script |
| B6 lands while a consumer's plugin update is already in flight | Low | Medium (that consumer is on `./src/claude` and cannot revert on their own) | PR body states the rollback contract; this is accepted risk, not fully mitigable, per ADR-109's own Rollback section |
| A later class's PR omits its own symlink or containment check, assuming skills' checks cover it | Medium without the reminder | High (a path-traversal or symlink write escapes the allowlist) | ADR-109 section 6 and DESIGN-025's Decision-rule Traceability table both name this as DR8, a per-class obligation; each task's Testing Requirements lists the symlink case explicitly |
| CODEOWNERS additions across B1, B2, B4, B5 do not actually block a merge, since the default-branch ruleset carries `require_code_owner_review: false` | Medium | Medium (review routes correctly but does not gate) | Same mitigation as the B4 ruleset risk; the plan does not assume CODEOWNERS alone is a gate |
| B1's agent composition drops content on first render, since 18 of 31 pairs already diverge (1,414 lines Claude-only, 622 shared-template-only, plus a two-file frontmatter divergence) | Medium without the fixture test | High (silent loss of Claude-only guidance across up to 18 agents) | A dedicated losslessness test renders all 31 variant pairs from their B1-initial templates and asserts byte-identity against a pre-B1 snapshot of both `src/claude/*.md` and `src/copilot-cli/agents/`, frontmatter included; content reconciliation into shared partials is explicitly deferred, never bundled into B1 |
| B4's narrower hooks class (16 of 23 tracked files: 13 executables plus `hooks.json`, `dispatch_groups.json`, and `markdownlint-safe-config.yaml`) is misread as "all of `.claude/hooks/`" during implementation | Low with the scope note, high without it | Medium (a doc file gets accidentally templated or a real hook script gets left out) | TASK-034's Objective and Files Affected name the excluded 7 doc files explicitly, not merely the included count |

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-09-11 | Six migration PRs, one per class, in the order agents, rules, remaining skills, hooks and settings, lib, marketplace switch | ADR-109 section 7: agents first to close the largest measured drift gap (D2); marketplace switch last because it is the customer-visible cut | One PR for every class; two PRs (mechanism, then content) per class as ADR-108 used |
| 2026-09-11 | Binplace manifest as a new YAML file under `templates/platforms/`, introduced in B1 rather than B0 | The manifest's shape only matters once a second output hop (plugin tree to install tree) exists for a real class; agents is the first class that needs it | Introducing the manifest in B0 alongside the ADR text, with no row until B1 |
| 2026-09-11 | `assert_no_claude_writes`'s allowlist reads the manifest at run time rather than a second hardcoded set | ADR-109 section 6: "the allowlist... generalizes to an allowlist equal to the binplace manifest"; a second set would drift from the manifest the same way the two lib mirrors drifted from each other | A hardcoded allowlist updated by hand in each class's PR |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-09-11 | ADR-109 written, reviewed, and accepted by the owner (PR #5745); spec artifacts (REQ-026, DESIGN-025, TASK-031 through TASK-036, ontology fragment, this plan) drafted in worktree `adr109-spec` on branch `feat/adr-109-spec-and-plan` | claude |

## Blockers

- ADR-109 is `accepted` (2026-09-11); the owner authorized implementation once PR #5745 lands, with Haiku and Sonnet agents building and Opus reviewing.
- B3's batching plan (count, size, grouping) is an open question the owner has not yet answered.
- B4's code-owner-review ruleset decision is an open question the owner has not yet answered.

## Deferred items

- Migrating `.github/prompts/`'s 21 non-`pr-quality-gate` files to a template.
- Any narrowing of REQ-003 D8's conditional (custom instructions generation pending Copilot CLI's `applyTo:` consumption); ADR-109 leaves this unchanged and this plan does not reopen it.
- A symmetric co-change gate as a stopgap for any class between its PR merging and the next class starting; ADR-109's Alternative E considered and rejected this as insufficient on its own.

## Related

- ADR: ADR-109 (supersedes ADR-052 at acceptance; amends ADR-107 property 1 and REQ-003 D4, D9, REQ-003-010)
- Prior art: ADR-108, REQ-025, DESIGN-024, TASK-030, TASK-025, and the completed plan `.agents/plans/completed/5706-skill-guidance-excerpts.md`, whose compile-and-drift-gate shape this plan generalizes
- Issues named in ADR-109 References: #5282, #5307, #5686, #5688, #5689, #5294, #5298, #4871, #1918, #2267, #5706
