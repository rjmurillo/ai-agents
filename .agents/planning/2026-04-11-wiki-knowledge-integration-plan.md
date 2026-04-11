# Plan: Wiki Knowledge Integration

## Overview

Bring 227 markdown files (5.6MB, 30 domains) from `~/Documents/Mobile/wiki/concepts` into ai-agents3 as passive context resources. Skills and agents @import these resources. No skill logic changes in this plan -- only knowledge injection.

## Objectives

- [ ] Map all 12 wiki domain groups to target skills/agents
- [ ] Produce compressed resource files (<8KB each, pipe-delimited format)
- [ ] Wire @import references into SKILL.md and agent .md files
- [ ] Resolve duplication conflicts (4 known overlaps)
- [ ] Validate token budget compliance for all modified files

## Scope

### In Scope

- Passive context resource files under `.claude/skills/<name>/resources/` or `src/claude/resources/`
- @import additions to SKILL.md and agent .md frontmatter/body
- Compression of wiki source content to pipe-delimited format
- Domain-to-target mapping decisions
- Duplication policy decisions for 4 known overlaps

### Out of Scope

- Skill logic changes (triggers, process steps, scripts)
- New skill creation
- Agent behavior changes
- Test cases (QA domain)
- Any edits to `~/Documents/Mobile/wiki/` source files

---

## Key Design Decisions (Pre-Milestone)

Answer these before Milestone 2 begins. They gate all downstream work.

### Decision 1: Resource directory layout

Two options:

| Option | Path | Tradeoff |
|--------|------|----------|
| A | `.claude/skills/<name>/resources/<file>.md` | Collocated, discoverable, matches existing `references/` pattern in some skills |
| B | `.agents/knowledge/<domain>/<file>.md` | Shared across skills/agents, avoids duplication when multiple consumers exist |

**Recommendation**: Hybrid. Per-skill `resources/` for content used by one skill. Shared `.agents/knowledge/` for content used by 3+ consumers.

### Decision 2: Duplication policy

Four confirmed overlaps:

| Wiki File | Existing Skill | Recommended Action |
|-----------|---------------|--------------------|
| `Cynefin Framework.md` | cynefin-classifier | Skip import; skill already encodes the framework |
| `Chesterton's Fence.md` | chestertons-fence | Skip import; redundant |
| `Buy vs Build Framework.md` | buy-vs-build-framework | Diff first; import only novel content as supplement |
| `Prompting/` files | prompt-engineer | Diff first; import anti-patterns not already covered |

### Decision 3: Compression format

Use the pipe-delimited format produced by context-optimizer's `compress_markdown_content.py`. Target: 60-80% token reduction. Each output file must be <8KB.

---

## Domain-to-Target Mapping

| Wiki Domain | Files | Primary Target | Secondary Target |
|-------------|-------|---------------|-----------------|
| Strategic Thinking | 54 | architect agent, high-level-advisor agent | buy-vs-build-framework skill, cynefin-classifier skill |
| AI Productivity | 26 | analyst agent, orchestrator agent | planner skill, memory skill |
| Design Principles | 27 | implementer agent, architect agent | code-qualities-assessment skill, golden-principles skill |
| Modernization | 26 | implementer agent | architect agent |
| Architectural Patterns | 15 | architect agent | cva-analysis skill |
| Mental Models | 10 | high-level-advisor agent, independent-thinker agent | decision-critic skill, chestertons-fence skill |
| Observability | 5 | observability skill | analyst agent |
| Reliability | 5 | slo-designer skill, chaos-experiment skill | architect agent |
| Build/Deploy/Ops | 19 | devops agent (src/claude/) | observability skill |
| Prompting & AI Safety | 5 | prompt-engineer skill | security agent |
| Team/Career/Leadership | 10 | high-level-advisor agent | independent-thinker agent |
| Critical Thinking | 3 | decision-critic skill | independent-thinker agent |

**Total files targeted**: 227 across 12 domains, ~30 target files (skills + agents).

---

## Milestones

### Milestone 1: Triage and Mapping
**Status**: [PENDING]
**Goal**: Decide which of 227 files to include, skip, or merge. Produce a manifest.
**Estimated Effort**: 2 days (based on 227 files at ~5 min/file triage = ~19h)
**Can Parallelize With**: Nothing. Gates all other milestones.

**Deliverables**:
- [ ] `wiki-integration-manifest.csv` listing each file: include/skip/merge, target skill/agent, rationale
- [ ] 4 duplication decisions documented (per Decision 2 above)
- [ ] Resource directory layout decision documented (per Decision 1 above)

**Acceptance Criteria**:
- [ ] All 227 files have an include/skip/merge disposition
- [ ] No target file projected to exceed 8KB after compression
- [ ] Duplication conflicts resolved with written rationale
- [ ] Manifest reviewed and approved before Milestone 2 starts

**Dependencies**: None

---

### Milestone 2: Compression Pipeline Setup
**Status**: [PENDING]
**Goal**: Validate that context-optimizer's compression script handles wiki markdown. Establish reproducible batch compression workflow.
**Estimated Effort**: 1 day (context-optimizer already exists; this is validation + scripting, not new work)
**Can Parallelize With**: Milestone 1 (can run script validation while triage proceeds)

**Deliverables**:
- [ ] Test compression on 5 representative files (1 per size/complexity tier)
- [ ] Confirm output format matches pipe-delimited spec
- [ ] Batch script or Makefile target that processes all "include" files from manifest
- [ ] Size validation step that fails if any output exceeds 8KB

**Acceptance Criteria**:
- [ ] 5 test files compressed to <8KB with no semantic loss verified by human review
- [ ] Batch script runs end-to-end without manual intervention
- [ ] Output files pass context-optimizer's compliance validator

**Dependencies**: None (runs parallel with Milestone 1)

---

### Milestone 3: Strategic Thinking + AI Productivity Resources (High-Value Domains)
**Status**: [PENDING]
**Goal**: Deliver the two highest-value domain groups first. These directly augment architect, analyst, high-level-advisor, and planner -- the most-invoked agents/skills.
**Estimated Effort**: 3 days (80 files, ~50 included after triage, compression + wiring)
**Can Parallelize With**: Milestone 4, 5 (after Milestone 1 and 2 complete)

**Deliverables**:
- [ ] Compressed resource files for Strategic Thinking domain (est. 20-25 files after triage)
- [ ] Compressed resource files for AI Productivity domain (est. 15-18 files after triage)
- [ ] @import additions to: `architect.md`, `analyst.md`, `high-level-advisor.md`, `planner/SKILL.md`
- [ ] Resource files placed per layout decision from Milestone 1

**Acceptance Criteria**:
- [ ] All resource files <8KB
- [ ] @import paths resolve (no broken references)
- [ ] Each target file's total context load <32KB (skill + all imports)
- [ ] architect agent can answer OODA/Wardley questions using imported context (manual smoke test)

**Dependencies**: Milestone 1 (manifest), Milestone 2 (compression pipeline)

---

### Milestone 4: Design + Modernization + Architectural Patterns Resources
**Status**: [PENDING]
**Goal**: Deliver engineering-practice domains. These augment implementer, code-qualities-assessment, cva-analysis, and golden-principles.
**Estimated Effort**: 3 days (68 files across 3 domains, ~45 included after triage)
**Can Parallelize With**: Milestone 3, 5

**Deliverables**:
- [ ] Compressed resource files for Design Principles (est. 18-20 files)
- [ ] Compressed resource files for Modernization (est. 18-20 files)
- [ ] Compressed resource files for Architectural Patterns (est. 10-12 files)
- [ ] @import additions to: `implementer.md`, `architect.md`, `code-qualities-assessment/SKILL.md`, `cva-analysis/SKILL.md`, `golden-principles/SKILL.md`

**Acceptance Criteria**:
- [ ] All resource files <8KB
- [ ] No duplicate content between Design Principles resources and existing golden-principles skill body
- [ ] implementer agent imports verified via manual probe (GoF pattern question answered correctly)

**Dependencies**: Milestone 1 (manifest), Milestone 2 (compression pipeline)

---

### Milestone 5: Observability + Reliability + Build/Deploy Resources
**Status**: [PENDING]
**Goal**: Deliver ops-domain knowledge to observability, slo-designer, chaos-experiment skills and devops agent.
**Estimated Effort**: 2 days (29 files, ~22 included after triage)
**Can Parallelize With**: Milestone 3, 4

**Deliverables**:
- [ ] Compressed resource files for Observability (est. 4-5 files)
- [ ] Compressed resource files for Reliability (est. 4-5 files)
- [ ] Compressed resource files for Build/Deploy/Ops (est. 12-14 files)
- [ ] @import additions to: `observability/SKILL.md`, `slo-designer/SKILL.md`, `chaos-experiment/SKILL.md`, `devops.md`

**Acceptance Criteria**:
- [ ] All resource files <8KB
- [ ] slo-designer skill references SLO/SLI/SLA definitions from imported resource (manual probe)
- [ ] No overlap with existing chaos-experiment skill's built-in framework content

**Dependencies**: Milestone 1 (manifest), Milestone 2 (compression pipeline)

---

### Milestone 6: Mental Models + Critical Thinking + Leadership Resources
**Status**: [PENDING]
**Goal**: Deliver the remaining three domain groups. Smaller volume; augment reasoning-focused agents.
**Estimated Effort**: 2 days (23 files, ~18 included after triage)
**Can Parallelize With**: Milestone 3, 4, 5

**Deliverables**:
- [ ] Compressed resource files for Mental Models (est. 8-9 files)
- [ ] Compressed resource files for Critical Thinking (est. 2-3 files)
- [ ] Compressed resource files for Team/Career/Leadership (est. 7-8 files)
- [ ] @import additions to: `high-level-advisor.md`, `independent-thinker.md`, `decision-critic/SKILL.md`
- [ ] Chesterton's Fence and Cynefin skip decisions implemented (no files created for those)

**Acceptance Criteria**:
- [ ] All resource files <8KB
- [ ] Chesterton's Fence and Cynefin Framework wiki files NOT imported (redundant per Decision 2)
- [ ] decision-critic skill references mental model resources via @import

**Dependencies**: Milestone 1 (manifest), Milestone 2 (compression pipeline)

---

### Milestone 7: Prompting + AI Safety Resources
**Status**: [PENDING]
**Goal**: Augment prompt-engineer skill and security agent with wiki anti-patterns.
**Estimated Effort**: 1 day (5 files; smallest domain)
**Can Parallelize With**: Milestone 6

**Deliverables**:
- [ ] Compressed resource files for Prompting and AI Safety (est. 3-4 files after dedup against prompt-engineer skill)
- [ ] @import additions to: `prompt-engineer/SKILL.md`, `security.md`

**Acceptance Criteria**:
- [ ] No content duplicated between new resources and existing prompt-engineer SKILL.md body
- [ ] All files <8KB

**Dependencies**: Milestone 1 (manifest), Milestone 2 (compression pipeline)

---

### Milestone 8: Integration Validation
**Status**: [PENDING]
**Goal**: Verify all @import chains load, no broken references, no context budget violations.
**Estimated Effort**: 1 day
**Can Parallelize With**: Nothing. Final gate.

**Deliverables**:
- [ ] Script that resolves all @import paths in modified SKILL.md and agent .md files
- [ ] Report: total token load per modified file (must be <32KB each)
- [ ] Manual smoke tests for 5 representative queries (one per major domain injected)
- [ ] Updated `HANDOFF.md` noting new resource directories and import conventions

**Acceptance Criteria**:
- [ ] 0 broken @import paths
- [ ] 0 files exceed 32KB total context load
- [ ] 5/5 smoke test queries return answers grounded in imported wiki content
- [ ] Compression ratio across all resources: 60% minimum token reduction vs raw source

**Dependencies**: Milestones 3-7 complete

---

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Wiki files contain personal/sensitive info not suited for repo | Medium | High | Manual review step in Milestone 1 triage; exclude any PII or org-confidential content |
| Compression distorts meaning of nuanced frameworks (Wardley, OODA) | Medium | Medium | Human review of compressed output for Milestone 3 files specifically |
| @import chain increases latency noticeably for heavy agents | Low | Medium | Measure token load in Milestone 8; split large imports across demand-loaded resources if needed |
| Triage underestimates relevant files; scope expands mid-stream | Medium | Low | Manifest is a gate artifact; changes require explicit revision, not silent scope creep |
| Some wiki files are outdated vs. existing skill content | Low | Low | Triage step explicitly diffs; skip file if skill content is newer/richer |

---

## Dependencies

- `context-optimizer` skill and its `compress_markdown_content.py` script must be functional (Milestone 2 validates this)
- Write access to `~/Documents/Mobile/wiki/concepts` for reading source files
- No external team dependencies; all work is local to this repo

---

## Sequencing Summary

```
Milestone 1 (Triage)
Milestone 2 (Compression Pipeline)   ← parallel with M1
    |
    +-- Milestone 3 (Strategic + AI Productivity)  ---|
    +-- Milestone 4 (Design + Modernization + Arch)    |-- parallel
    +-- Milestone 5 (Obs + Reliability + Ops)          |
    +-- Milestone 6 (Mental Models + Leadership)    ---|
    +-- Milestone 7 (Prompting + Safety)            ---|
    |
Milestone 8 (Integration Validation)
```

**Critical path**: M1 + M2 + any single content milestone + M8 = 8 days minimum.
**Full parallel execution** (M3-M7 concurrent after M1+M2): ~9 days total.
**Sequential execution** (one content milestone at a time): ~14 days total.

---

## Success Criteria

- [ ] All 227 wiki files triaged (include/skip/merge disposition)
- [ ] Resource files created for all "include" dispositions
- [ ] 0 broken @import references across repo
- [ ] 0 resource files exceed 8KB
- [ ] 60%+ token reduction vs raw source across all compressed files
- [ ] 5 smoke test queries pass (grounded in imported knowledge)
- [ ] No duplication between resource content and existing skill body content

---

## Pre-PR Validation Work Package

**Assignee**: QA Agent
**Blocking**: PR creation
**Estimated Effort**: 1-2 hours

### Tasks

#### Task 1: @import Reference Audit
- [ ] Resolve all @import paths in modified files
- [ ] Verify no broken references
- [ ] Verify no circular imports

#### Task 2: Token Budget Validation
- [ ] Measure total context load per modified skill/agent file
- [ ] Flag any file exceeding 32KB
- [ ] Confirm all resource files <8KB individually

#### Task 3: Content Deduplication Check
- [ ] Verify Cynefin and Chesterton's Fence wiki files were NOT imported
- [ ] Verify no resource content duplicates existing SKILL.md body text (>50% overlap)

#### Task 4: Compression Compliance
- [ ] Confirm pipe-delimited format on all resource files
- [ ] Confirm 60%+ token reduction vs source

#### Task 5: Smoke Test Execution
- [ ] Run 5 representative queries against modified agents/skills
- [ ] Document responses; verify grounding in wiki-sourced content

### Acceptance Criteria

- All 5 validation tasks complete with evidence
- 0 blocking issues
- QA provides APPROVED verdict to orchestrator before PR opens
