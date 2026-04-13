# Plan: Knowledge Integration into Skills and Agents (v2 -- Proof-First)

## Overview

Prove that domain knowledge in skill `references/` directories measurably improves
agent output quality. Start with 20-30 high-value files targeting the 5 highest-traffic
skills. Measure before/after. Scale only what clears the quality bar.

**Sources**: Personal wiki (227 files), Osmani agent-skills (21), gstack skills (35).

**Mechanism**: Summarized reference files in `.claude/skills/<name>/references/`,
referenced from `## References` or `## Resources` tables in SKILL.md.
Uses the `references/` convention per SkillForge and SKILL-AUTHORING standards
(not `resources/` which is a planner-only anomaly).

**Key change from v1**: v1 planned bulk import of 283 files across 6 milestones.
CEO review (both Codex and Claude subagent) independently concluded the plan
optimized for artifact production, not outcomes. Revised to proof-first with
a hard kill gate.

## Objectives

- [ ] Baseline agent quality measured on 5 target skills (before resources)
- [ ] 20-30 high-value resource files created and injected into 5 target skills
- [ ] After-injection quality measured on same 5 skills with same prompts
- [ ] Kill gate: measurable improvement demonstrated OR effort stops
- [ ] Every resource file under 8KB; every skill total under 40KB (AC-2, AC-3)
- [ ] Every SKILL.md `## Resources` table matches `references/` directory contents (AC-4, AC-5)
- [ ] No SKILL.md exceeds 500 lines (AC-8)
- [ ] Scale decision made with evidence (proceed to full scope or stop)

## Scope

### Phase 1 Scope (This Plan)

- 5 target skills: architect, implementer, analyze, planner, decision-critic
- 20-30 resource files from highest-value wiki domains + Osmani + gstack
- Before/after quality measurement with documented prompts and rubric
- Kill gate decision

### Phase 2 Scope (Contingent on Phase 1 Success)

- Remaining wiki files (manifest, triage, bulk injection)
- Remaining Osmani/gstack mappings
- New skill creation via SkillForge (only if Phase 1 proves demand)
- Full validation gate

### Out of Scope

- Skill triggers, scripts, or process step changes
- Agent prompt modifications beyond resource table entries
- Wiki source edits
- Automated wiki-to-repo sync
- gstack browser runtime code (patterns only)
- New skill creation (deferred to Phase 2)

---

## Milestones

### Milestone 1: Baseline Measurement
**Status**: [PENDING]
**Goal**: Establish quality baseline for 5 target skills before any resources added.
**Effort**: S (half day)

**Target skills** (must be actual skills with SKILL.md, not agents):
1. `analyze` -- AI Productivity, debugging, code review
2. `decision-critic` -- Mental Models, Critical Thinking
3. `threat-modeling` -- Architectural Patterns, security frameworks
4. `cva-analysis` -- Design Principles
5. `golden-principles` -- Design Principles, engineering practices

Note: `architect` and `implementer` are agents in `src/claude/`, not skills.
They lack SKILL.md and references/ directories. Deferred to Phase 2 if
references/ proves effective for skills first. `planner` excluded because
it already has references/ (confounds the baseline).

**M0 Result (COMPLETED)**: references/ files are NOT auto-loaded into context.
They are demand-loaded. The SKILL.md must contain explicit `See references/file.md`
pointers. The agent reads reference files when the skill's instructions direct it to.

This is confirmed by examining 10+ existing skills (cynefin-classifier, cva-analysis,
buy-vs-build-framework, memory, github, merge-resolver, etc.). All use the same
pattern: SKILL.md contains path references, agent reads on demand.

**Implications for this plan**:
- 40KB per-skill cap is NOT a concern (files load one at a time, not all at once)
- SKILL.md must add explicit "See references/X.md" instructions at relevant process steps
- Reference files should be structured for on-demand reading (self-contained, actionable)
- The quality measurement must test whether agents actually READ the references when
  they should, not just whether the files exist

**Deliverables**:
- [ ] Resources/ auto-loading verified (M0 probe test passes)
- [ ] 6 domain-specific prompts per skill (30 total) documented
- [ ] Baseline responses captured and scored on a 1-5 rubric (accuracy, depth, specificity)
- [ ] Rubric with anchor examples for each score level documented at `.agents/planning/quality-rubric.md`
- [ ] Summarization methodology defined: prompt template, model, quality checklist

**Acceptance Criteria**:
- [ ] M0 probe test passes (references/ mechanism verified)
- [ ] 30 prompts documented with expected answers
- [ ] 30 baseline responses captured with scores
- [ ] Average baseline score per skill documented
- [ ] Summarization prompt and checklist documented before M2 starts
- [ ] Resource file conventions documented: naming (`<domain>-<topic>.md`, kebab-case),
      YAML frontmatter (`source`, `created`, `review-by`), size limit (8KB)
- [ ] SKILL-AUTHORING.md updated with references/ pattern and conventions
- [ ] Resource size validation script created (pre-commit or CI)

**Dependencies**: None

---

### Milestone 2: Resource Selection and Creation (20-30 files)
**Status**: [PENDING]
**Goal**: Select the highest-value knowledge from all 3 sources. Summarize and inject
  into the 5 target skills. Prioritize by expected impact on baseline scores.
**Effort**: M (2 days)

**Selection criteria** (Pareto: 20% of files delivering 80% of value):
- Wiki: Strategic Thinking (OODA, Wardley, Systems Thinking), Design Principles
  (GoF, SOLID, TDD), Mental Models (Gall's Law, Chesterton's Fence), top .NET patterns
- Osmani: source-driven-development, api-and-interface-design, performance-optimization,
  debugging-and-error-recovery, context-engineering
- gstack: investigate (root cause methodology), review (pre-landing patterns),
  cso (security audit methodology), office-hours (structured questioning)

**Deliverables**:
- [ ] 20-30 resource files created, each under 8KB
- [ ] Each placed in target skill's `references/` directory
- [ ] `## Resources` table added/updated in each target SKILL.md
- [ ] Resource paths verified (AC-5)

**Acceptance Criteria**:
- [ ] All files under 8KB (AC-2)
- [ ] No skill exceeds 40KB total resources (AC-3)
- [ ] All SKILL.md files under 500 lines (AC-8)
- [ ] Resources table matches directory contents (AC-4)

**Dependencies**: M1 (baseline established)

---

### Milestone 3: After-Injection Measurement and Kill Gate
**Status**: [PENDING]
**Goal**: Re-run the same 15 prompts against the 5 skills now equipped with resources.
  Compare to baseline. Decide whether to scale.
**Effort**: S (half day)

**Deliverables**:
- [ ] 30 after-injection responses captured and scored with same rubric
- [ ] Per-skill delta documented (before vs after)
- [ ] Quality improvement report at `.agents/planning/quality-results.md`

**Kill gate criteria** (heuristic evaluation, not statistical test):
- [ ] PROCEED: at least 4 of 5 skills show median improvement >= 0.5 with no skill regressing
- [ ] CONDITIONAL: 3 of 5 skills improve >= 0.5, proceed only for improving skills
- [ ] STOP: median improvement <= 0 OR fewer than 3 skills improve. Investigate root cause.

Note: This is a qualitative judgment call with structured evidence, not a
statistical test. n=6 per skill provides directional signal, not p-values.
Run baseline and after-injection on the same day to control for model drift.

**Acceptance Criteria**:
- [ ] All 15 prompts re-run and scored
- [ ] Kill gate decision documented with evidence
- [ ] If PROCEED: Phase 2 plan produced with prioritized file list based on M3 learnings

**Dependencies**: M2 (resources injected)

---

### Milestone 4: Scale Decision (Contingent)
**Status**: [BLOCKED on M3 kill gate]
**Goal**: If kill gate passes, expand to full scope using evidence from Phase 1.

**Scope** (only if M3 passes):
- Wiki manifest for remaining files
- Remaining Osmani/gstack mappings
- New skill creation via SkillForge (only for skills where M3 showed clear value)
- Full validation gate

**This milestone is NOT planned in detail until M3 evidence is available.**

---

## Sequencing

```
M1: Baseline Measurement    (Day 1, half day)
    |
M2: Resource Creation       (Days 1-3)
    |
M3: After-Injection + Gate  (Day 3, half day)
    |
M4: Scale Decision          (Day 4+, contingent on M3)
```

**Critical path**: M1 + M2 + M3 = 3 days to kill gate.
**If gate passes**: Phase 2 planning adds 1 day, execution adds 5-7 days.
**If gate fails**: 3 days invested, early exit with evidence. No wasted bulk work.

---

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Baseline measurement is subjective | Medium | Medium | Documented rubric with 1-5 scale, multiple prompts per skill |
| 20-30 files is too few to show signal | Medium | Medium | Target highest-value files; if signal is weak, the full batch would be weaker |
| Summarization strips semantic meaning | Medium | Medium | Compare summary quality across sources during M2; iterate format |
| Resources loaded but ignored by skills | Medium | High | If M3 shows no improvement, this is the likely cause; investigate routing |
| Kill gate creates sunk cost pressure | Low | Medium | Pre-commit: if < 0.5 improvement, STOP regardless of effort invested |
| Internal .NET content in Modernization files | Medium | High | Triage during M2 selection; only include clearly non-internal patterns |

---

## Task Count

| Milestone | Tasks |
|-----------|-------|
| M1 Baseline | 3 |
| M2 Resource Creation | 5 |
| M3 After-Injection + Gate | 3 |
| M4 Scale Decision | TBD |
| **Total (Phase 1)** | **11 tasks across 3 milestones** |

---

## Success Criteria (Phase 1)

- [ ] Baseline quality measured for 5 skills (15 prompts, scored)
- [ ] 20-30 resource files created and injected
- [ ] After-injection quality measured with same prompts
- [ ] Kill gate decision made with documented evidence
- [ ] All resource files under 8KB, all skill totals under 40KB
- [ ] No SKILL.md exceeds 500 lines

---

## Decision Audit Trail

<!-- AUTONOMOUS DECISION LOG -->

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|---------------|-----------|-----------|----------|
| 1 | CEO | Revise from bulk import to proof-first | User Challenge | P1 (completeness via evidence) | Both Codex and Claude subagent independently concluded bulk import optimizes for artifacts, not outcomes. No baseline exists. | Bulk import of 283 files without measurement |
| 2 | CEO | Defer new skill creation to Phase 2 | Mechanical | P4 (DRY) | 5 of 9 proposed skills already exist as global gstack skills. Creating repo-local duplicates before proving demand is scope theater. | Create 9 skills upfront |
| 3 | CEO | Target 5 highest-traffic skills | Mechanical | P3 (pragmatic) | Proves the concept where it matters most. architect, implementer, analyze, planner, decision-critic cover the broadest domain set. | All 25+ skills simultaneously |
| 4 | CEO | Hard kill gate at < 0.5 improvement | Mechanical | P6 (bias toward action) | Prevents sunk cost continuation. 3 days invested is acceptable loss. | Soft gate with "conditional proceed" for all thresholds |
| 5 | Eng | Replace architect/implementer (agents) with actual skills in target list | Mechanical | P5 (explicit) | Codex P0: architect and implementer are agents in src/claude/, not skills. They lack SKILL.md and references/. | Keep agents as targets |
| 6 | Eng | Add M0 probe test to verify references/ auto-loading | Mechanical | P3 (pragmatic) | Both voices flagged: references/ loading is asserted, not proven. One test file proves the mechanism before 20-30 files. | Assume it works |
| 7 | Eng | Increase to 6 prompts per skill, reframe as heuristic not statistical | Mechanical | P5 (explicit) | Both voices: n=3 is not meaningful. n=6 provides directional signal. Reframed as qualitative judgment. | Keep n=3 or require n=50 |
| 8 | Eng | Recalibrate kill gate to median >= 0.5 on 4/5 skills | Mechanical | P3 (pragmatic) | Codex: >= 1.0 average is too blunt on 1-5 ordinal scale. Median >= 0.5 on 4/5 skills is decision-aligned. | Keep >= 1.0 average |
| 9 | Eng | Require summarization methodology defined before M2 | Mechanical | P1 (completeness) | Both voices: "summarize for LLM efficiency" is undefined. Prompt, model, and checklist must exist pre-M2. | Define during M2 |
| 10 | Eng | Add prompt injection review gate for external content | Taste | P5 (explicit) | Claude subagent: external repos could contain directive-like language. Human review of summarized content before merge. | Trust external sources |
| 11 | DX | Add resource file conventions to M1 deliverables | Mechanical | P1 (completeness) | Both voices: naming, format, frontmatter all undefined. Define before creating files. | Define ad hoc during M2 |
| 12 | DX | Require YAML frontmatter on every resource file | Mechanical | P5 (explicit) | Both voices: no source, created, or review-by metadata. Staleness is invisible without it. | No metadata |
| 13 | DX | Add resource size validation to pre-commit or CI | Mechanical | P1 (completeness) | Both voices: 8KB/40KB limits exist as ACs but have no enforcement mechanism. | Manual review only |
| 14 | DX | Update SKILL-AUTHORING.md with references/ pattern | Mechanical | P5 (explicit) | Both voices: pattern is not documented anywhere a skill author would find it. | Undocumented convention |
| 15 | Gate | Use references/ not resources/ per SkillForge convention | Mechanical | P4 (DRY) | SkillForge generates references/. SKILL CLAUDE.md says "Move reference documentation to references/". planner's resources/ is the anomaly. | Use resources/ |

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | issues_open | 2 critical: no outcome measurement, bulk import without evidence. Revised to proof-first. |
| Eng Review | `/plan-eng-review` | Architecture & tests | 1 | issues_open | 1 P0: agents vs skills confusion. 11 findings total. references/ not resources/. |
| DX Review | `/plan-devex-review` | Developer experience | 1 | issues_open | 5/5 dimensions failed. No naming, no enforcement, no docs. Fixes added to M1. |
| CEO Voices | codex+subagent | Independent challenge | 1 | issues_open | 6/6 consensus: plan optimized for artifacts not outcomes. |
| Eng Voices | codex+subagent | Architecture challenge | 1 | issues_open | 4/6 consensus. P0: target list mixed agents and skills. |
| DX Voices | codex+subagent | DX challenge | 1 | clean | 5/5 consensus. All fixes applied. |

**VERDICT:** APPROVED with 15 auto-decisions, 1 user challenge resolved (proof-first), 1 taste decision (prompt injection review gate). Ready for `/build`.

## Handoff

Phase 1 plan complete. 3 milestones, ~14 tasks, 3-day critical path to kill gate.
Phase 2 scope is deliberately unplanned until M3 evidence is available.
Key prerequisite: M0 probe test must verify references/ auto-loading before any other work.
