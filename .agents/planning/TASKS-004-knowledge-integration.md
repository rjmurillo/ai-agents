# Task Breakdown: Knowledge Integration into Skills and Agents

## Source

- Plan: `.agents/planning/004-knowledge-integration-plan.md`

## Summary

| Complexity | Count |
|------------|-------|
| S          | 5     |
| M          | 11    |
| L          | 2     |
| **Total**  | **18** |

---

## Tasks

### Milestone 1: Pipeline Proof

**Goal**: Prove the end-to-end pipeline on 5 files before committing to 283 more.

---

#### TASK-001

**ID**: TASK-001
**Milestone**: M1
**Type**: Spike
**Complexity**: M

**Description**
Create 5 representative resource files (one per source type) to validate the summarization pipeline produces LLM-efficient content under 8KB.

**Acceptance Criteria**
- [ ] 5 files exist: 1 wiki, 1 Osmani, 1 gstack, 1 .NET, 1 mental model
- [ ] `find .claude/skills/*/resources -name "*.md" -size +8k | wc -l` returns 0
- [ ] Each file reads as a coherent, standalone LLM reference (no raw dump)

**Dependencies**
- None

**Files Affected**
- `.claude/skills/<target>/resources/<name>.md`: 5 new resource files

---

#### TASK-002

**ID**: TASK-002
**Milestone**: M1
**Type**: Chore
**Complexity**: S

**Description**
Update one SKILL.md with a `## Resources` table entry pointing to a file created in TASK-001.

**Acceptance Criteria**
- [ ] Target SKILL.md contains a `## Resources` table with at least one row
- [ ] Row path resolves to an existing file (manual check: `ls` the referenced path)
- [ ] SKILL.md line count is under 500

**Dependencies**
- TASK-001: Resource file must exist before referencing it

**Files Affected**
- `.claude/skills/<target>/SKILL.md`: Resources table added

---

#### TASK-003

**ID**: TASK-003
**Milestone**: M1
**Type**: Chore
**Complexity**: S

**Description**
Document the size validation command and AC-7 smoke test template so another agent can repeat the pipeline without ambiguity.

**Acceptance Criteria**
- [ ] Size validation command documented: `find .claude/skills/*/resources -name "*.md" -size +8k | wc -l`
- [ ] AC-7 smoke test template includes: prompt text, expected answer pattern, pass/fail criterion
- [ ] Documentation is placed in `.agents/planning/` or a referenced location in the plan

**Dependencies**
- TASK-001: Pipeline must run at least once to validate the documented steps

**Files Affected**
- `.agents/planning/pipeline-runbook.md`: New runbook file

---

#### TASK-004

**ID**: TASK-004
**Milestone**: M1
**Type**: Feature
**Complexity**: S

**Description**
Run 5 smoke test probes against the 5 resource files to confirm answers are grounded in resource content, not general training data.

**Acceptance Criteria**
- [ ] 5 prompts documented with expected answers
- [ ] 5/5 actual responses cite or match content from the resource file
- [ ] Results recorded in `.agents/planning/pipeline-runbook.md`

**Dependencies**
- TASK-001: Resource files must exist to test against
- TASK-003: Smoke test template must be defined before execution

**Files Affected**
- `.agents/planning/pipeline-runbook.md`: Smoke test results appended

---

### Milestone 2: New Skill Creation (SkillForge)

**Goal**: Create 9 new skill scaffolds so M4 has valid target directories.

---

#### TASK-005

**ID**: TASK-005
**Milestone**: M2
**Type**: Chore
**Complexity**: S

**Description**
Verify which of the 9 target skills already exist before invoking SkillForge to prevent duplicates.

**Acceptance Criteria**
- [ ] `ls .claude/skills/` output reviewed against the 9 skill names
- [ ] `analysis-provenance` confirmed as existing or absent
- [ ] Verified-existing skills removed from the SkillForge creation list
- [ ] List of skills to create is finalized in writing

**Dependencies**
- TASK-004: M1 must be complete (pipeline proven) before M2 starts

**Files Affected**
- None (read-only verification step)

---

#### TASK-006

**ID**: TASK-006
**Milestone**: M2
**Type**: Feature
**Complexity**: M

**Description**
Invoke SkillForge to scaffold each skill not already present, producing valid SKILL.md frontmatter and an empty `resources/` directory for each.

**Acceptance Criteria**
- [ ] Each new skill directory exists under `.claude/skills/<name>/`
- [ ] Each new SKILL.md passes frontmatter validation (required fields present)
- [ ] Each skill has an empty `resources/` subdirectory
- [ ] No skills from the verified-existing list are recreated
- [ ] Skills created: subset of `idea-refine`, `benchmark`, `canary`, `design-shotgun`, `design-html`, `devex-review`, `careful-guard`, `office-hours` (per TASK-005 findings)

**Dependencies**
- TASK-005: Verified list of skills to create

**Files Affected**
- `.claude/skills/<name>/SKILL.md`: New files for each created skill
- `.claude/skills/<name>/resources/`: New empty directories

---

#### TASK-007

**ID**: TASK-007
**Milestone**: M2
**Type**: Chore
**Complexity**: S

**Description**
Validate all new skill scaffolds pass AC-10: frontmatter valid, `resources/` directory present, no duplicate skills.

**Acceptance Criteria**
- [ ] `ls .claude/skills/` lists all expected new skills
- [ ] Each SKILL.md contains required frontmatter keys
- [ ] `find .claude/skills/*/resources -maxdepth 0 -type d` confirms directories exist
- [ ] Zero pre-existing skills were overwritten

**Dependencies**
- TASK-006: Scaffolds must be created before validation

**Files Affected**
- None (read-only validation)

---

### Milestone 3: Wiki Manifest

**Goal**: Produce `wiki-manifest.csv` with a disposition for all 227 wiki files.

---

#### TASK-008

**ID**: TASK-008
**Milestone**: M3
**Type**: Spike
**Complexity**: M

**Description**
Enumerate all 227 wiki files and assign initial domain classifications using the spec's domain-to-target mapping table.

**Acceptance Criteria**
- [ ] All 227 files listed with `domain` and `file_path` columns populated
- [ ] Domain assignments follow the spec mapping (no ad-hoc classifications)
- [ ] Partial CSV saved to `.agents/planning/wiki-manifest.csv` after enumeration

**Dependencies**
- TASK-004: M1 must be complete (pipeline proven) before M3 starts

**Files Affected**
- `.agents/planning/wiki-manifest.csv`: Created with partial data

---

#### TASK-009

**ID**: TASK-009
**Milestone**: M3
**Type**: Feature
**Complexity**: L

**Description**
Assign `disposition` (include/merge/skip), `target`, and `rationale` for every wiki file, front-loading skip decisions to reduce downstream injection scope.

**Acceptance Criteria**
- [ ] `wc -l wiki-manifest.csv` returns 228 (header + 227 rows)
- [ ] `csvtool col 4 wiki-manifest.csv | grep -c '^$'` returns 0 (no blank dispositions)
- [ ] All Modernization domain files reviewed for internal content; suspect files marked `skip`
- [ ] Cynefin and Chesterton's Fence files marked `skip` (redundant with existing skills)
- [ ] Estimated resource byte count per target skill documented; no skill projected to exceed 40KB

**Dependencies**
- TASK-008: File enumeration and domain classification must be complete

**Files Affected**
- `.agents/planning/wiki-manifest.csv`: All columns fully populated

---

#### TASK-010

**ID**: TASK-010
**Milestone**: M3
**Type**: Chore
**Complexity**: S

**Description**
Validate wiki-manifest.csv passes all AC-1 checks and the Modernization pre-check before M5 consumes it.

**Acceptance Criteria**
- [ ] `wc -l wiki-manifest.csv` = 228
- [ ] Blank disposition count = 0
- [ ] All Modernization `include` files have rationale column entries explaining internal-content review
- [ ] Validation result recorded as [PASS] or [FAIL] with evidence

**Dependencies**
- TASK-009: Manifest must be fully populated before validation

**Files Affected**
- None (read-only validation; results appended to runbook or plan)

---

### Milestone 4: Osmani + gstack Injection

**Goal**: Place resource files for all 56 external skill mappings.

Note: Steps 1-5 below are a parameterized operation repeated for each of the 56 mapping rows. Tasks represent pipeline stages, not per-resource work items.

---

#### TASK-011

**ID**: TASK-011
**Milestone**: M4
**Type**: Feature
**Complexity**: L

**Description**
For each of the 56 Osmani/gstack mapping rows, read the source skill content, summarize to under 8KB, and write the resource file to the correct `resources/` directory.

**Acceptance Criteria**
- [ ] 21 Osmani resource files exist in their target skill `resources/` directories
- [ ] 35 gstack resource files exist in their target skill `resources/` directories
- [ ] `find .claude/skills/*/resources -name "*.md" -size +8k | wc -l` returns 0
- [ ] `open-gstack-browser` and `gstack-upgrade` confirmed skipped (meta/utility per spec)

**Dependencies**
- TASK-007: New skill directories must exist before placing resources in them

**Files Affected**
- `.claude/skills/<target>/resources/<source-name>.md`: 56 new resource files

---

#### TASK-012

**ID**: TASK-012
**Milestone**: M4
**Type**: Feature
**Complexity**: M

**Description**
Add a row to the `## Resources` table in each affected SKILL.md for every resource file placed in TASK-011.

**Acceptance Criteria**
- [ ] Every resource file from TASK-011 has a corresponding row in its target SKILL.md Resources table
- [ ] No SKILL.md exceeds 500 lines after table additions
- [ ] No target skill's total `resources/` directory exceeds 40KB

**Dependencies**
- TASK-011: Resource files must exist before referencing them in tables

**Files Affected**
- `.claude/skills/<target>/SKILL.md`: Resources table rows added for each affected skill

---

#### TASK-013

**ID**: TASK-013
**Milestone**: M4
**Type**: Chore
**Complexity**: S

**Description**
Verify AC-2, AC-3, AC-4, AC-8, and AC-9 pass for all M4 outputs before proceeding to M6.

**Acceptance Criteria**
- [ ] 56 resource files confirmed present (AC-9)
- [ ] All files under 8KB (AC-2)
- [ ] No skill total resources exceed 40,960 bytes (AC-3)
- [ ] Each resource listed in its target SKILL.md Resources table (AC-4)
- [ ] All affected SKILL.md files under 500 lines (AC-8)
- [ ] Validation result recorded as [PASS] or [FAIL]

**Dependencies**
- TASK-012: Table entries must be in place before cross-checking directory vs. table

**Files Affected**
- None (read-only validation)

---

### Milestone 5: Wiki Injection

**Goal**: Place resource files for all wiki files with `include` or `merge` disposition.

Note: Steps 1-5 are a parameterized operation repeated for each manifest row with disposition `include` or `merge`.

---

#### TASK-014

**ID**: TASK-014
**Milestone**: M5
**Type**: Feature
**Complexity**: M

**Description**
For each `include` manifest row, read the wiki source, summarize to under 8KB, and write the resource file to the target skill's `resources/` directory.

**Acceptance Criteria**
- [ ] One resource file exists per `include` row in the manifest
- [ ] All files under 8KB (AC-2)
- [ ] No target skill exceeds 40KB total resources (AC-3)

**Dependencies**
- TASK-007: New skill directories must exist
- TASK-010: Manifest must be validated before consuming it

**Files Affected**
- `.claude/skills/<target>/resources/<slug>.md`: New resource files per include row

---

#### TASK-015

**ID**: TASK-015
**Milestone**: M5
**Type**: Feature
**Complexity**: M

**Description**
For each `merge` manifest row group, consolidate multiple wiki source files into one resource file and write it to the target skill's `resources/` directory.

**Acceptance Criteria**
- [ ] One output file exists per merge group (multiple sources, one output)
- [ ] All merged files under 8KB (AC-2)
- [ ] No target skill exceeds 40KB total (AC-3)
- [ ] Merged files are coherent references, not concatenations

**Dependencies**
- TASK-007: New skill directories must exist
- TASK-010: Manifest must be validated before consuming it

**Files Affected**
- `.claude/skills/<target>/resources/<slug>.md`: Merged resource files per merge group

---

#### TASK-016

**ID**: TASK-016
**Milestone**: M5
**Type**: Feature
**Complexity**: M

**Description**
Add `## Resources` table rows to all SKILL.md files affected by wiki injection (include and merge outputs).

**Acceptance Criteria**
- [ ] Every resource file from TASK-014 and TASK-015 has a table row in its target SKILL.md
- [ ] No SKILL.md exceeds 500 lines (AC-8)
- [ ] Agent definition files updated where wiki resources target agents rather than skills

**Dependencies**
- TASK-014: Include resource files must exist
- TASK-015: Merge resource files must exist

**Files Affected**
- `.claude/skills/<target>/SKILL.md`: Resources table rows added

---

#### TASK-017

**ID**: TASK-017
**Milestone**: M5
**Type**: Chore
**Complexity**: S

**Description**
Grep all Modernization-domain resource files for internal markers (team names, internal tool names, internal URLs) and confirm zero matches.

**Acceptance Criteria**
- [ ] Grep for known internal marker patterns returns 0 matches across all `resources/` files (AC-6)
- [ ] Result recorded as [PASS] or [FAIL] with the grep command used

**Dependencies**
- TASK-016: All wiki resource files must be placed and referenced before the sweep

**Files Affected**
- None (read-only scan)

---

### Milestone 6: Validation Gate

**Goal**: Prove all 10 acceptance criteria pass before the PR opens.

---

#### TASK-018

**ID**: TASK-018
**Milestone**: M6
**Type**: Chore
**Complexity**: M

**Description**
Execute the full AC-1 through AC-10 validation suite and record pass/fail evidence for each criterion.

**Acceptance Criteria**
- [ ] AC-1: `wc -l wiki-manifest.csv` = 228; blank disposition count = 0 [PASS]
- [ ] AC-2: `find .claude/skills/*/resources -name "*.md" -size +8k | wc -l` = 0 [PASS]
- [ ] AC-3: Per-skill resource size sum script returns zero skills over 40,960 bytes [PASS]
- [ ] AC-4: `ls resources/` vs SKILL.md table comparison returns zero mismatches per skill [PASS]
- [ ] AC-5: Path resolution script exits with code 0 [PASS]
- [ ] AC-6: Internal marker grep returns 0 matches in `resources/` files [PASS]
- [ ] AC-7: 5 smoke tests with documented prompts and expected answers return 5/5 pass [PASS]
- [ ] AC-8: `wc -l` on all modified SKILL.md files; none exceed 500 [PASS]
- [ ] AC-9: 56 external resource files confirmed present [PASS]
- [ ] AC-10: 9 new skill directories with valid SKILL.md frontmatter confirmed [PASS]
- [ ] QA agent returns APPROVED verdict to orchestrator
- [ ] No BLOCKED items remain

**Dependencies**
- TASK-013: M4 outputs validated
- TASK-017: M5 outputs validated (including internal marker sweep)

**Files Affected**
- `.agents/planning/pipeline-runbook.md`: Validation evidence appended

---

## Dependency Graph

```
TASK-001 (M1: create 5 samples)
  → TASK-002 (M1: update 1 SKILL.md)
  → TASK-003 (M1: document pipeline + smoke template)
      → TASK-004 (M1: run smoke tests)
          → TASK-005 (M2: verify existing skills)   ← also starts TASK-008 (M3) in parallel
              → TASK-006 (M2: SkillForge create)
                  → TASK-007 (M2: validate scaffolds)
                      → TASK-011 (M4: write 56 resource files)
                          → TASK-012 (M4: update SKILL.md tables)
                              → TASK-013 (M4: validate M4 outputs)
                      → TASK-014 (M5: include injection)  ← requires TASK-010
                      → TASK-015 (M5: merge injection)    ← requires TASK-010
                          → TASK-016 (M5: update SKILL.md tables)
                              → TASK-017 (M5: internal marker grep)
TASK-004 → TASK-008 (M3: enumerate wiki files)
    → TASK-009 (M3: assign dispositions)
        → TASK-010 (M3: validate manifest)
            → TASK-014, TASK-015 (M5: inject)

TASK-013 + TASK-017 → TASK-018 (M6: full validation gate)
```

**Parallel tracks after TASK-004**:
- M2 (TASK-005 to TASK-007) and M3 (TASK-008 to TASK-010) run concurrently.
- M4 starts after TASK-007 (new skills exist).
- M5 starts after TASK-007 and TASK-010 (new skills exist and manifest is ready).
- M4 and M5 can overlap.

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Summarization strips semantic meaning | Resource fails smoke test | AC-7 smoke tests run against M1 samples before scale-out; adjust summarization approach if any fail |
| Internal .NET content leaks into resources | AC-6 failure at M6 | TASK-009 flags suspect files before injection; TASK-017 sweeps after injection |
| Token budget overrun per skill | AC-3 failure at M6 | TASK-013 and TASK-017 run per-skill size checks after M4 and M5, not only at M6 |
| New skill count grows beyond 9 | Scope creep | TASK-005 hard-checks the list; additions require explicit spec change |
| SKILL.md line count creeps past 500 | AC-8 failure | TASK-012 and TASK-016 check line count after every table addition batch |

---

## Estimate Reconciliation

**Source Document**: `004-knowledge-integration-plan.md`
**Source Estimate**: 33 tasks across 6 milestones (from plan Task Count table)
**Derived Task Count**: 18 tasks
**Difference**: -45% (18 vs 33)
**Status**: Reconciled
**Rationale**: The plan's 33-task count treated M4 and M5 parameterized operations as multiple tasks (e.g., 5 tasks each for M4 and M5 pipeline stages multiplied across resources). Per the decomposition constraint, parameterized operations become one task per pipeline stage. M4's 5 pipeline steps collapse to 3 tasks (write files, update tables, validate). M5 splits include and merge into separate tasks (different logic) then adds table updates and the internal-marker sweep. M6's 10 ACs collapse into 1 validation task. The 18-task count reflects genuinely discrete, independently verifiable work items.
