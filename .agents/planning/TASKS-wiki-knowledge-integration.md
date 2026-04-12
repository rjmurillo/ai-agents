# Task Breakdown: Wiki Knowledge Integration

## Source
- Plan: `.agents/planning/2026-04-11-wiki-knowledge-integration-plan.md`
- Wiki root: `~/Documents/Mobile/wiki/concepts/`
- Wiki file count: 227 files across 28 domains

## Summary

| Complexity | Count |
|------------|-------|
| S          | 18    |
| M          | 14    |
| L          | 4     |
| **Total**  | **36** |

---

## Tasks

### Milestone 1: Triage and Manifest

**Goal**: Produce a manifest that gates all content injection work. No M3-M7 work starts without this.

---

#### TASK-001: Enumerate all wiki files into a flat manifest CSV

**ID**: TASK-001
**Type**: Chore
**Complexity**: S
**Parallel**: Yes (no dependencies)

**Description**
Walk `~/Documents/Mobile/wiki/concepts/` recursively. Produce a CSV with columns: `domain`, `file`, `size_bytes`, `disposition` (blank). Save to `.agents/planning/wiki-manifest.csv`.

**Acceptance Criteria**
- [ ] CSV exists at `.agents/planning/wiki-manifest.csv`
- [ ] Row count matches `find ~/Documents/Mobile/wiki/concepts -name "*.md" | wc -l`
- [ ] Columns present: `domain`, `file`, `size_bytes`, `disposition`
- [ ] All `disposition` cells are blank (triage done in TASK-002)

**Files Affected**
- `.agents/planning/wiki-manifest.csv`: created

---

#### TASK-002: Triage Strategic Thinking domain (54 files)

**ID**: TASK-002
**Type**: Chore
**Complexity**: M
**Parallel**: After TASK-001
**Dependencies**
- TASK-001: manifest CSV required

**Description**
Review all 54 files in `Strategic Thinking/`. Assign each a disposition: `include`, `merge`, or `skip`. Map `include`/`merge` files to target skills: `architect`, `analyst`, `high-level-advisor`, `planner`, `cynefin-classifier`, `buy-vs-build-framework`, `decision-critic`, `pre-mortem`.

**Acceptance Criteria**
- [ ] All 54 rows in manifest have a non-blank `disposition`
- [ ] Each `include`/`merge` row has a `target_skill` column populated
- [ ] At least 1 file mapped to each of the 8 target skills listed above
- [ ] `skip` rationale column populated for all skipped files

**Files Affected**
- `.agents/planning/wiki-manifest.csv`: rows updated

---

#### TASK-003: Triage AI Productivity domain (26 files)

**ID**: TASK-003
**Type**: Chore
**Complexity**: S
**Parallel**: After TASK-001, parallel with TASK-002
**Dependencies**
- TASK-001: manifest CSV required

**Description**
Review all 26 files in `AI Productivity/`. Assign dispositions. Map to: `prompt-engineer`, `context-optimizer`, `memory` skills.

**Acceptance Criteria**
- [ ] All 26 rows have non-blank `disposition` and `target_skill`
- [ ] `skip` rationale populated where applicable

**Files Affected**
- `.agents/planning/wiki-manifest.csv`: rows updated

---

#### TASK-004: Triage Design Principles domain (27 files)

**ID**: TASK-004
**Type**: Chore
**Complexity**: S
**Parallel**: After TASK-001, parallel with TASK-002/003
**Dependencies**
- TASK-001: manifest CSV required

**Description**
Review all 27 files in `Design Principles/`. Map to: `implementer`, `cva-analysis`, `golden-principles`, `code-qualities-assessment`.

**Acceptance Criteria**
- [ ] All 27 rows have non-blank `disposition` and `target_skill`
- [ ] `skip` rationale populated where applicable

**Files Affected**
- `.agents/planning/wiki-manifest.csv`: rows updated

---

#### TASK-005: Triage Architectural Patterns domain (15 files)

**ID**: TASK-005
**Type**: Chore
**Complexity**: S
**Parallel**: After TASK-001, parallel with TASK-002-004
**Dependencies**
- TASK-001: manifest CSV required

**Description**
Review all 15 files in `Architectural Patterns/`. Map to: `architect`, `threat-modeling`.

**Acceptance Criteria**
- [ ] All 15 rows have non-blank `disposition` and `target_skill`
- [ ] `skip` rationale populated where applicable

**Files Affected**
- `.agents/planning/wiki-manifest.csv`: rows updated

---

#### TASK-006: Triage Mental Models and Critical Thinking domains (10 + 3 files)

**ID**: TASK-006
**Type**: Chore
**Complexity**: S
**Parallel**: After TASK-001, parallel with TASK-002-005
**Dependencies**
- TASK-001: manifest CSV required

**Description**
Review 13 files across `Mental Models/` and `Critical Thinking/`. Map to: `critic`, `chestertons-fence`, `independent-thinker` (if it exists; else `critic`).

**Acceptance Criteria**
- [ ] All 13 rows have non-blank `disposition` and `target_skill`
- [ ] `skip` rationale populated where applicable

**Files Affected**
- `.agents/planning/wiki-manifest.csv`: rows updated

---

#### TASK-007: Triage Observability and Reliability domains (5 + 5 files)

**ID**: TASK-007
**Type**: Chore
**Complexity**: S
**Parallel**: After TASK-001, parallel with TASK-002-006
**Dependencies**
- TASK-001: manifest CSV required

**Description**
Review 10 files across `Observability/` and `Reliability/`. Map to: `observability`, `slo-designer`, `chaos-experiment`.

**Acceptance Criteria**
- [ ] All 10 rows have non-blank `disposition` and `target_skill`
- [ ] `skip` rationale populated where applicable

**Files Affected**
- `.agents/planning/wiki-manifest.csv`: rows updated

---

#### TASK-008: Triage remaining domains (Modernization 26, Prompting 2, AI Safety 3, AI Strategy 1, Career 2, Team 8, others 24)

**ID**: TASK-008
**Type**: Chore
**Complexity**: M
**Parallel**: After TASK-001, parallel with TASK-002-007
**Dependencies**
- TASK-001: manifest CSV required

**Description**
Review ~66 files across Modernization, Prompting, AI Safety, AI Strategy, Career, Team Operations, Team Culture, Engineering Leadership, Change Management, and all other small domains. Most Modernization files are Microsoft-internal: mark as `skip`. Map Prompting/AI Safety to `prompt-engineer`. Map Career/Leadership to `high-level-advisor`, `retrospective`.

**Acceptance Criteria**
- [ ] All rows for these domains have non-blank `disposition` and `target_skill` (or `skip` rationale)
- [ ] Modernization skip rate documented in manifest notes column

**Files Affected**
- `.agents/planning/wiki-manifest.csv`: rows updated

---

#### TASK-009: Validate manifest completeness and generate summary report

**ID**: TASK-009
**Type**: Chore
**Complexity**: S
**Parallel**: No, after TASK-002 through TASK-008
**Dependencies**
- TASK-002 through TASK-008: all triage complete

**Description**
Run a script that verifies every row in the manifest has a non-blank `disposition`. Produce a summary: include count, merge count, skip count, files per target skill. Save to `.agents/planning/wiki-manifest-summary.md`.

**Acceptance Criteria**
- [ ] Script exits 0 (no blank dispositions)
- [ ] Summary file exists at `.agents/planning/wiki-manifest-summary.md`
- [ ] Summary lists include/merge/skip counts by domain
- [ ] Summary lists file count per target skill

**Files Affected**
- `.agents/planning/wiki-manifest-summary.md`: created

---

### Milestone 2: Compression Pipeline Validation

**Goal**: Prove the pipe-delimited compression approach works before bulk injection. Runs parallel with M1.

---

#### TASK-010: Select 3 representative wiki files for compression trial

**ID**: TASK-010
**Type**: Spike
**Complexity**: S
**Parallel**: Yes (no dependencies)

**Description**
Choose one large file (>8KB), one medium file (~4KB), one small file (<2KB) from different domains. Document their raw sizes and chosen compression targets. Record selections in `.agents/planning/compression-trial-inputs.md`.

**Acceptance Criteria**
- [ ] 3 files selected, one from each size tier
- [ ] Raw byte size recorded for each
- [ ] Target skill identified for each
- [ ] Selections documented in `.agents/planning/compression-trial-inputs.md`

**Files Affected**
- `.agents/planning/compression-trial-inputs.md`: created

---

#### TASK-011: Compress trial files to pipe-delimited format

**ID**: TASK-011
**Type**: Feature
**Complexity**: M
**Parallel**: After TASK-010
**Dependencies**
- TASK-010: input files identified

**Description**
Apply the context-optimizer pipe-delimited compression format to all 3 trial files. Follow the pattern established in the `context-optimizer` skill. Save compressed outputs to `.agents/planning/compression-trial-outputs/`.

**Acceptance Criteria**
- [ ] 3 compressed files exist in `.agents/planning/compression-trial-outputs/`
- [ ] Each compressed file is under 8KB (verify with `wc -c`)
- [ ] No file loses its core concepts (manual spot-check against source)
- [ ] Compression ratio documented: `(original - compressed) / original * 100`

**Files Affected**
- `.agents/planning/compression-trial-outputs/*.md`: created (3 files)

---

#### TASK-012: Validate agent usability of compressed content

**ID**: TASK-012
**Type**: Spike
**Complexity**: M
**Parallel**: After TASK-011
**Dependencies**
- TASK-011: compressed files exist

**Description**
For each compressed file: ask the target skill agent a question that requires the compressed content to answer correctly. Verify the agent produces a coherent, accurate response. Document pass/fail per file with example prompt and response snippet in `.agents/planning/compression-trial-results.md`.

**Acceptance Criteria**
- [ ] All 3 files produce [PASS] result (agent answers correctly)
- [ ] Results documented with prompt and response snippet
- [ ] Any [FAIL] includes root cause and proposed fix
- [ ] Results file saved at `.agents/planning/compression-trial-results.md`

**Files Affected**
- `.agents/planning/compression-trial-results.md`: created

---

### Milestone 3: Strategic and AI Domains

**Goal**: Inject Strategic Thinking (54 files) and AI Productivity (26 files) into target skills. Starts after M1+M2.

**Prerequisites**: TASK-009 [PASS], TASK-012 [PASS]

---

#### TASK-013: Create `.agents/knowledge/` directory structure

**ID**: TASK-013
**Type**: Chore
**Complexity**: S
**Parallel**: Yes (runs once, gates TASK-014 onward)
**Dependencies**
- TASK-009: manifest complete
- TASK-012: compression validated

**Description**
Create the shared knowledge directory at `.agents/knowledge/`. Create subdirectories per domain group: `strategic/`, `ai-productivity/`, `design/`, `architecture/`, `mental-models/`, `observability/`, `reliability/`. Add a `README.md` in each explaining its contents and which skills @import it.

**Acceptance Criteria**
- [ ] `.agents/knowledge/` exists with 7 subdirectories
- [ ] Each subdirectory has a `README.md`
- [ ] README lists target skills that @import from that directory

**Files Affected**
- `.agents/knowledge/*/README.md`: created (7 files)

---

#### TASK-014: Compress and stage Strategic Thinking content

**ID**: TASK-014
**Type**: Feature
**Complexity**: L
**Parallel**: After TASK-013
**Dependencies**
- TASK-002: Strategic Thinking triage complete
- TASK-013: directory structure exists

**Description**
For all `include`/`merge` files in Strategic Thinking: apply pipe-delimited compression. Stage compressed files into `.agents/knowledge/strategic/`. Files marked `merge` get merged into a single topic file. Expected output: 5-10 compressed topic files covering the strategic thinking corpus.

**Acceptance Criteria**
- [ ] All `include` files from manifest are represented in `.agents/knowledge/strategic/`
- [ ] All `merge` files are consolidated (no 1:1 copies of source files)
- [ ] Every output file is under 8KB (`wc -c` check)
- [ ] Compressed file count matches manifest include+merge count (after merges)
- [ ] No Microsoft-internal content included

**Files Affected**
- `.agents/knowledge/strategic/*.md`: created

---

#### TASK-015: Inject strategic knowledge into target skill SKILL.md files

**ID**: TASK-015
**Type**: Feature
**Complexity**: M
**Parallel**: After TASK-014
**Dependencies**
- TASK-014: compressed files exist

**Description**
Add `@import` directives to the SKILL.md of each target skill: `architect`, `analyst`, `high-level-advisor`, `planner`, `cynefin-classifier`, `buy-vs-build-framework`, `decision-critic`, `pre-mortem`. Each skill imports only the relevant subset of `.agents/knowledge/strategic/` files.

**Acceptance Criteria**
- [ ] Each target skill SKILL.md contains at least 1 `@import` pointing to `.agents/knowledge/strategic/`
- [ ] No skill imports a file irrelevant to its purpose
- [ ] Each SKILL.md remains under 500 lines after import additions
- [ ] `git diff` shows only @import line additions, no deletions of existing content

**Files Affected**
- `.claude/skills/architect/SKILL.md`
- `.claude/skills/analyst/SKILL.md`
- `.claude/skills/high-level-advisor/SKILL.md`
- `.claude/skills/planner/SKILL.md`
- `.claude/skills/cynefin-classifier/SKILL.md`
- `.claude/skills/buy-vs-build-framework/SKILL.md`
- `.claude/skills/decision-critic/SKILL.md`
- `.claude/skills/pre-mortem/SKILL.md`

---

#### TASK-016: Compress and inject AI Productivity content

**ID**: TASK-016
**Type**: Feature
**Complexity**: M
**Parallel**: After TASK-013, parallel with TASK-014
**Dependencies**
- TASK-003: AI Productivity triage complete
- TASK-013: directory structure exists

**Description**
Compress all `include`/`merge` AI Productivity files into `.agents/knowledge/ai-productivity/`. Add `@import` directives to `prompt-engineer`, `context-optimizer`, and `memory` skill SKILL.md files.

**Acceptance Criteria**
- [ ] All output files in `.agents/knowledge/ai-productivity/` are under 8KB
- [ ] `prompt-engineer`, `context-optimizer`, `memory` SKILL.md files each have at least 1 @import
- [ ] Each SKILL.md remains under 500 lines
- [ ] No `include`/`merge` file from manifest is missing from output

**Files Affected**
- `.agents/knowledge/ai-productivity/*.md`: created
- `.claude/skills/prompt-engineer/SKILL.md`
- `.claude/skills/context-optimizer/SKILL.md`
- `.claude/skills/memory/SKILL.md`

---

### Milestone 4: Design and Architecture Domains

**Goal**: Inject Design Principles (27 files) and Architectural Patterns (15 files). Starts after M1+M2.

**Prerequisites**: TASK-009 [PASS], TASK-012 [PASS]

---

#### TASK-017: Compress and inject Design Principles content

**ID**: TASK-017
**Type**: Feature
**Complexity**: M
**Parallel**: After TASK-013, parallel with M3 tasks
**Dependencies**
- TASK-004: Design Principles triage complete
- TASK-013: directory structure exists

**Description**
Compress all `include`/`merge` Design Principles files into `.agents/knowledge/design/`. Add `@import` directives to `implementer`, `cva-analysis`, `golden-principles`, `code-qualities-assessment` SKILL.md files.

**Acceptance Criteria**
- [ ] All output files under 8KB
- [ ] 4 target skills each have at least 1 @import added
- [ ] Each SKILL.md remains under 500 lines
- [ ] No `include`/`merge` file from manifest missing from output

**Files Affected**
- `.agents/knowledge/design/*.md`: created
- `.claude/skills/implementer/SKILL.md`
- `.claude/skills/cva-analysis/SKILL.md`
- `.claude/skills/golden-principles/SKILL.md`
- `.claude/skills/code-qualities-assessment/SKILL.md`

---

#### TASK-018: Compress and inject Architectural Patterns content

**ID**: TASK-018
**Type**: Feature
**Complexity**: M
**Parallel**: After TASK-013, parallel with TASK-017
**Dependencies**
- TASK-005: Architectural Patterns triage complete
- TASK-013: directory structure exists

**Description**
Compress all `include`/`merge` Architectural Patterns files into `.agents/knowledge/architecture/`. Add `@import` directives to `architect` and `threat-modeling` SKILL.md files.

**Acceptance Criteria**
- [ ] All output files under 8KB
- [ ] `architect` and `threat-modeling` SKILL.md files each have at least 1 @import added
- [ ] Each SKILL.md remains under 500 lines
- [ ] No `include`/`merge` file from manifest missing from output

**Files Affected**
- `.agents/knowledge/architecture/*.md`: created
- `.claude/skills/architect/SKILL.md`
- `.claude/skills/threat-modeling/SKILL.md`

---

### Milestone 5: Observability and Reliability Domains

**Goal**: Inject Observability (5 files) and Reliability (5 files). Starts after M1+M2.

**Prerequisites**: TASK-009 [PASS], TASK-012 [PASS]

---

#### TASK-019: Compress and inject Observability and Reliability content

**ID**: TASK-019
**Type**: Feature
**Complexity**: S
**Parallel**: After TASK-013, parallel with M3/M4 tasks
**Dependencies**
- TASK-007: Observability/Reliability triage complete
- TASK-013: directory structure exists

**Description**
Compress all `include`/`merge` files from both domains. Stage into `.agents/knowledge/observability/` and `.agents/knowledge/reliability/`. Add @import to `observability`, `slo-designer`, and `chaos-experiment` SKILL.md files.

**Acceptance Criteria**
- [ ] Both output directories contain compressed files, all under 8KB
- [ ] 3 target skill SKILL.md files each have at least 1 @import added
- [ ] Each SKILL.md remains under 500 lines

**Files Affected**
- `.agents/knowledge/observability/*.md`: created
- `.agents/knowledge/reliability/*.md`: created
- `.claude/skills/observability/SKILL.md`
- `.claude/skills/slo-designer/SKILL.md`
- `.claude/skills/chaos-experiment/SKILL.md`

---

### Milestone 6: Mental Models and Critical Thinking

**Goal**: Inject Mental Models (10 files) and Critical Thinking (3 files). Starts after M1+M2.

**Prerequisites**: TASK-009 [PASS], TASK-012 [PASS]

---

#### TASK-020: Compress and inject Mental Models and Critical Thinking content

**ID**: TASK-020
**Type**: Feature
**Complexity**: S
**Parallel**: After TASK-013, parallel with M3/M4/M5 tasks
**Dependencies**
- TASK-006: Mental Models/Critical Thinking triage complete
- TASK-013: directory structure exists

**Description**
Compress all `include`/`merge` files. Stage into `.agents/knowledge/mental-models/`. Add @import to `critic` and `chestertons-fence` SKILL.md files. If `independent-thinker` skill does not exist, map those files to `critic` instead.

**Acceptance Criteria**
- [ ] Output files in `.agents/knowledge/mental-models/` all under 8KB
- [ ] `critic` and `chestertons-fence` SKILL.md files each have at least 1 @import
- [ ] If `independent-thinker` skill exists, it also has @import; if not, `critic` covers the content
- [ ] Each SKILL.md remains under 500 lines

**Files Affected**
- `.agents/knowledge/mental-models/*.md`: created
- `.claude/skills/critic/SKILL.md`
- `.claude/skills/chestertons-fence/SKILL.md`

---

### Milestone 7: Remaining Domains

**Goal**: Handle Prompting, AI Safety, AI Strategy, Career, Team, and other small domains selectively.

**Prerequisites**: TASK-009 [PASS], TASK-012 [PASS]

---

#### TASK-021: Compress and inject Prompting and AI Safety content

**ID**: TASK-021
**Type**: Feature
**Complexity**: S
**Parallel**: After TASK-013, parallel with M3-M6 tasks
**Dependencies**
- TASK-008: Remaining domains triage complete
- TASK-013: directory structure exists

**Description**
Compress `include`/`merge` files from Prompting (2 files) and AI Safety (3 files). Stage into `.agents/knowledge/ai-productivity/` (same directory as AI Productivity per domain overlap). Add @import to `prompt-engineer` SKILL.md.

**Acceptance Criteria**
- [ ] Compressed files staged, all under 8KB
- [ ] `prompt-engineer` SKILL.md updated with @import
- [ ] No duplicate content with TASK-016 output

**Files Affected**
- `.agents/knowledge/ai-productivity/*.md`: appended/created
- `.claude/skills/prompt-engineer/SKILL.md`

---

#### TASK-022: Compress and inject Team and Career content

**ID**: TASK-022
**Type**: Feature
**Complexity**: S
**Parallel**: After TASK-013, parallel with M3-M6 tasks
**Dependencies**
- TASK-008: Remaining domains triage complete
- TASK-013: directory structure exists

**Description**
Compress `include`/`merge` files from Team Operations (5), Team Culture (3), Career (2), Engineering Leadership (3), Change Management (2). Stage into a new `.agents/knowledge/leadership/` directory. Add @import to `high-level-advisor` and `retrospective` SKILL.md files.

**Acceptance Criteria**
- [ ] `.agents/knowledge/leadership/` exists with compressed files, all under 8KB
- [ ] `high-level-advisor` and `retrospective` SKILL.md files each have at least 1 @import
- [ ] Each SKILL.md remains under 500 lines
- [ ] Modernization files confirmed as `skip` (zero Modernization files in output)

**Files Affected**
- `.agents/knowledge/leadership/*.md`: created
- `.claude/skills/high-level-advisor/SKILL.md`
- `.claude/skills/retrospective/SKILL.md`

---

### Milestone 8: Integration Validation

**Goal**: Verify the complete integration. All M3-M7 tasks must complete before this milestone.

**Prerequisites**: TASK-015, TASK-016, TASK-017, TASK-018, TASK-019, TASK-020, TASK-021, TASK-022 all [COMPLETE]

---

#### TASK-023: Verify all @import paths resolve

**ID**: TASK-023
**Type**: Chore
**Complexity**: S
**Parallel**: No, after all injection tasks
**Dependencies**
- All TASK-015 through TASK-022

**Description**
Write a script that reads every SKILL.md in `.claude/skills/`, extracts @import paths, and verifies each path exists on disk. Report any broken imports.

**Acceptance Criteria**
- [ ] Script exits 0 (all @import paths resolve to existing files)
- [ ] Zero broken import paths in output
- [ ] Script saved to `.agents/planning/scripts/verify-imports.py`

**Files Affected**
- `.agents/planning/scripts/verify-imports.py`: created

---

#### TASK-024: Verify all injected files are under 8KB

**ID**: TASK-024
**Type**: Chore
**Complexity**: S
**Parallel**: After all injection tasks, parallel with TASK-023
**Dependencies**
- All TASK-014 through TASK-022

**Description**
Run `find .agents/knowledge -name "*.md" -size +8k` and verify zero results. Document file sizes in `.agents/planning/knowledge-size-report.md`.

**Acceptance Criteria**
- [ ] Zero files in `.agents/knowledge/` exceed 8KB
- [ ] Size report exists at `.agents/planning/knowledge-size-report.md`
- [ ] Report includes file name, size in bytes, and domain

**Files Affected**
- `.agents/planning/knowledge-size-report.md`: created

---

#### TASK-025: Verify no SKILL.md exceeds 500 lines after injection

**ID**: TASK-025
**Type**: Chore
**Complexity**: S
**Parallel**: After all injection tasks, parallel with TASK-023/024
**Dependencies**
- All TASK-015 through TASK-022

**Description**
Check line count of every modified SKILL.md. Any file exceeding 500 lines requires either a `size-exception: true` frontmatter entry or refactoring.

**Acceptance Criteria**
- [ ] All modified SKILL.md files are under 500 lines, OR have `size-exception: true` in frontmatter
- [ ] List of all checked files and line counts saved to `.agents/planning/skill-size-report.md`

**Files Affected**
- `.agents/planning/skill-size-report.md`: created

---

#### TASK-026: Run agent smoke tests for each target skill

**ID**: TASK-026
**Type**: Chore
**Complexity**: L
**Parallel**: After TASK-023 [PASS]
**Dependencies**
- TASK-023: all imports resolve

**Description**
For each skill that received new @imports, ask one question that requires the injected knowledge to answer correctly. Document prompt, expected answer summary, actual response, and [PASS]/[FAIL] per skill. Save results to `.agents/planning/integration-smoke-test-results.md`.

Target skills to test (18 total): `architect`, `analyst`, `high-level-advisor`, `planner`, `cynefin-classifier`, `buy-vs-build-framework`, `decision-critic`, `pre-mortem`, `prompt-engineer`, `context-optimizer`, `memory`, `implementer`, `cva-analysis`, `golden-principles`, `code-qualities-assessment`, `threat-modeling`, `observability`, `slo-designer`, `chaos-experiment`, `critic`, `chestertons-fence`, `retrospective`.

**Acceptance Criteria**
- [ ] All target skills tested (one prompt each)
- [ ] Results file exists at `.agents/planning/integration-smoke-test-results.md`
- [ ] Zero [FAIL] results, OR each [FAIL] has a filed remediation note
- [ ] Overall [PASS] rate documented

**Files Affected**
- `.agents/planning/integration-smoke-test-results.md`: created

---

#### TASK-027: Update AGENTS.md or skill catalog with knowledge base location

**ID**: TASK-027
**Type**: Chore
**Complexity**: S
**Parallel**: After TASK-026 [PASS]
**Dependencies**
- TASK-026: smoke tests pass

**Description**
Add a reference to `.agents/knowledge/` in `AGENTS.md` under the Retrieval-Led Reasoning section. Document what the directory contains and how agents should use it.

**Acceptance Criteria**
- [ ] `AGENTS.md` references `.agents/knowledge/` in the Retrieval-Led Reasoning section
- [ ] Entry describes the directory purpose and pattern for use
- [ ] `git diff AGENTS.md` shows only additive changes

**Files Affected**
- `AGENTS.md`

---

## Dependency Graph

```
TASK-001
├── TASK-002 ─┐
├── TASK-003  │
├── TASK-004  │
├── TASK-005  │
├── TASK-006  │
├── TASK-007  │
└── TASK-008 ─┤
              └─ TASK-009

TASK-010 → TASK-011 → TASK-012

TASK-009 + TASK-012 →
  TASK-013 →
    ├── TASK-014 → TASK-015
    ├── TASK-016
    ├── TASK-017
    ├── TASK-018
    ├── TASK-019
    ├── TASK-020
    ├── TASK-021
    └── TASK-022
          │
          ▼
    TASK-023 + TASK-024 + TASK-025
          │
          ▼
    TASK-026
          │
          ▼
    TASK-027
```

**Parallel opportunities**:
- TASK-002 through TASK-008 run in parallel (all depend only on TASK-001)
- TASK-010 through TASK-012 run in parallel with TASK-001-009
- TASK-014 through TASK-022 run in parallel (all depend only on TASK-013)
- TASK-023, TASK-024, TASK-025 run in parallel

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Strategic Thinking domain is 54 files; some may overlap across target skills | Duplicate content in multiple @imports bloats context | During TASK-002, explicitly assign each file to exactly 1 skill; use merge consolidation for shared concepts |
| Compression loses nuance for complex frameworks (e.g., Cynefin) | Agent gives shallow answers | TASK-012 validation catches this before bulk injection; add detail back for failing content |
| SKILL.md 500-line limit hit after multiple @imports | Commit blocked by CI | Check line counts after each injection task; refactor to `references/` if needed (TASK-025 catches stragglers) |
| `high-level-advisor` or `retrospective` skill may not exist in `.claude/skills/` | TASK-022 has no target file | Pre-check in TASK-013; if missing, create stub SKILL.md before injection |
| Modernization domain (26 files) contains some non-Microsoft-internal content | Useful content skipped | TASK-008 triage must review each file individually; do not bulk-skip the domain |
| 227 files is a large corpus; compression may be inconsistent across contributors | Quality variance | Use the context-optimizer skill consistently; TASK-012 validates the pattern before bulk use |
