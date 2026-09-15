# Retrospective: epic-5456-m4-pr2-search-before-building

## Session Info
- **Date**: 2026-09-15
- **Agents**: implementer (this session)
- **Task Type**: Feature (control-plane subtraction, epic #5456 M4 PR2)
- **Outcome**: Success

## Phase 0: Data Gathering
### Work Items
- Read the merged M4 PR1 diff (`git show 55ec6212c`) as the pattern for this move: an ADR-108 partial for skill-owned content, plain `references/*.md` files for content that is skill-specific prose rather than a shared preamble
- Confirmed `programming-advisor`, `memory-search`, and `memory-gate` are not in the `PILOT` template-owned set (`tests/build_scripts/test_skill_templates_pilot_scope.py`), so their `SKILL.md` and new `references/*.md` files were edited directly
- Split `.claude/rules/search-before-building.md` into three new reference files by section: intro/When To Apply/The Three Layers/Quick Self-Review to `programming-advisor/references/search-before-building.md`; Where To Search to `memory-search/references/where-to-search.md` (pointing at the existing `bound-the-search.mustache` partial instead of duplicating its sentence); The Contradiction Log to `memory-gate/references/contradiction-log.md`
- Added one pointer line per destination `SKILL.md`, `git rm` the rule file, and discovered `templates/skills/partials/bound-the-search.mustache` pinned `rule-source: search-before-building.md`; removed that pin per ADR-108 section 5 ("a partial with no rule-source line is standalone, which is the shape a partial takes once a later issue cuts the rule text"), verified by `test_skill_partials_rule_parity.py`
- Retargeted five live cross-references found by a scoped grep (`.claude/rules/*.md`, `CLAUDE.md`, `AGENTS.md`, `.claude/skills/**/SKILL.md`, `docs/`, `templates/`): `builder-ethos.md`, `token-economy.md`, and the template-owned `ai-agents-research-methodology.SKILL.md.tmpl` (edited the template, not the rendered `SKILL.md`, since that skill is in the PILOT set)
- Ran `build/scripts/generate_rules.py` and `build/scripts/build_all.py` after the deletion, then again after later edits to `canonical-source-mirror.md` and the doctrine references (the first regen pass did not cover edits made afterward; caught by rerunning `build_all.py --check`)
- Measured the post-deletion always-on corpus live via `tests.validation.always_on_corpus_helpers` (`_budget`, `_tree_always_on`, `_source_bytes`) rather than subtracting the deleted file's own byte count from the PR1 baseline, because editing `builder-ethos.md` in the same change also shifted the always-on total: 3 rules, 43,895 bytes (mirror); 43,952 bytes, 57-byte delta (source); 5.4x/10.5x the 8KB multipliers
- Updated all four documents that restate those figures (`canonical-source-mirror.md`, `model-context-doctrine.md`, `rule-audit-procedure.md`, the `always-on-membership-lives-in-the-mirror` Serena memory) and lowered the `test_measured_always_on_set_is_not_empty` ratchet from 4 to 3
- Tightened `scripts/validation/rule_activation_coverage_baseline.json` (`--update-baseline`) to drop the now-nonexistent `search-before-building` entry
- Updated the M4 dispositions ledger (new `MERGE` row, gate 9 tally to `MERGE 2`) and the cohort plan (four `search-before-building.md` rows marked done, one destination corrected from the plan's `memory-gate` to the actually-used `programming-advisor`)
- Ran the full gate sequence: `test_always_on_corpus_claims.py`, `test_audit_procedure_claims.py`, `test_completion_terminal_contracts.py`, `tests/build_scripts` (2072 passed, 2 skipped), `skill_size.py --ci`, `check_skill_md_portability.py`, `check_skill_md_exec_portability.py`, `SKIP_AUTOFIX=1 pre_pr.py` (all clean, all exit 0)
- 11 commits, each 5 authored files or fewer (one commit carries a 6th file, the hook-generated `.serena/memories/memory-index.md`, which `AGENTS.md`'s atomic-commit boundary exempts)

### Commits
- f6f15994d docs(metrics): record M4 PR2 search-before-building disposition
- a63724637 chore(validation): tighten rule-activation-coverage baseline
- a0eea406f chore(build): regenerate mirrors for the updated always-on figures
- 3de9a7fa0 docs(rules): update always-on membership figures to 3 rules, 43,895 bytes
- 4b23a6a19 chore(build): prune search-before-building.instructions.md mirrors
- ec658a43c chore(build): regenerate mirrors for the retargeted cross-references
- d860348b2 refactor(rules): retarget search-before-building.md cross-references
- 37ac7b939 chore(build): regenerate copilot mirror for memory-gate contradiction log
- 329f7c2c0 chore(build): regenerate copilot mirrors for search-before-building move
- 15fb3bb34 docs(skills): point programming-advisor, memory-search, memory-gate at new references
- 612697bc2 feat(skills): add search-before-building reference files to three skills
- 55ec6212c refactor(rules): fold claude-model-patches into the build, test, plan, and ship skills (#5760)

## Phase 1: Insights Generated
[Five Whys output if failure]
[Fishbone output if complex]
[Patterns and Shifts output]
[Learning Matrix output]

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| [Strategy] | [Outcome] | [1-10] | [%] |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| [Strategy] | [Type] | [Cause] | [Fix] | [%] |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| [Situation] | [Save] | [Takeaway] |

## Phase 3: Decisions

### Action Classification
[Keep/Drop/Add/Modify table]

### SMART Validation
[Validation for each new skill]

### Action Sequence
[Ordered actions with dependencies]

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: ADR-108 partial rule-source pins (templates/skills/partials/*.mustache) must be dropped, not repointed, when the excerpted rule file is deleted; section 5 defines this as the partial becoming standalone.
- **Atomicity Score**: 45% (Needs Work)
- **Evidence**: [Execution detail]
- **Skill Operation**: ADD | UPDATE | TAG | REMOVE
- **Target Skill ID**: [If UPDATE/TAG/REMOVE]

### Learning 2
- **Statement**: Regenerate (build_all.py) after every edit to an always-on rule source, not only once after the initial deletion; editing builder-ethos.md later in the same change silently drifted its already-generated mirror until a second regen pass caught it.
- **Atomicity Score**: 0% (Rejected)
- **Evidence**: [Execution detail]
- **Skill Operation**: ADD | UPDATE | TAG | REMOVE
- **Target Skill ID**: [If UPDATE/TAG/REMOVE]

### Learning 3
- **Statement**: The always-on doctrine's guarded figures must be measured live via tests.validation.always_on_corpus_helpers rather than derived by subtracting the deleted file's own byte count from the prior total, because an unrelated always-on rule edited in the same change shifts the total by more than the deleted file's size.
- **Atomicity Score**: 0% (Rejected)
- **Evidence**: [Execution detail]
- **Skill Operation**: ADD | UPDATE | TAG | REMOVE
- **Target Skill ID**: [If UPDATE/TAG/REMOVE]

## Skillbook Updates

### ADD
```json
{
  "skill_id": "{domain}-{description}",
  "statement": "[Atomic]",
  "context": "[When to apply]",
  "evidence": "[Source]",
  "atomicity": [%]
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|

## Phase 5: Persist and Close

### Memory Persistence

| Learning | Atomicity | Existing Match | Result |
|----------|-----------|----------------|--------|
| [Learning] | [%] | [Memory name or none] | [Added / Updated / Deduplicated / Skipped / Failed] |

### +/Delta

#### + Keep
- [What worked well in this retrospective]

#### Delta Change
- [What should be different next time]

### Delta Triage

#### Actionable Items Identified

| Delta Item | Category | Priority | Destination | Reference |
|------------|----------|----------|-------------|-----------|
| [Item from Delta] | [Missing Docs/Tool Gap/Process/Feature] | P0/P1/P2/P3 | Issue #N / Memory / Skip | [Link] |

#### Issues Created

| Issue | Title | Priority | Labels |
|-------|-------|----------|--------|
| #[N] | [Title] | P0/P1 | enhancement, source:retrospective |

#### Backlog Items Stored

| Item | Priority | Memory File |
|------|----------|-------------|
| [Item] | P2/P3 | backlog/retro-YYYY-MM-DD-items.md |

#### Skipped Items

| Item | Reason |
|------|--------|
| [Item] | [Duplicate of #X / Not actionable / Already addressed] |

### ROTI Assessment

**Score**: [0-4]

**Benefits Received**:
- [Benefit 1]
- [Benefit 2]

**Time Invested**: [Duration]

**Verdict**: [Continue | Modify | Stop]

### Helped, Hindered, Hypothesis

#### Helped
- [What made this retrospective effective]

#### Hindered
- [What got in the way]

#### Hypothesis
- [Experiment to try next retrospective]
