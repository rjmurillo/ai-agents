---
type: task
id: TASK-005
title: Bundle Dedicated Skills into Lifecycle Commands
status: todo
priority: P1
complexity: M
related:
  - DESIGN-005
blocked_by: []
blocks: []
assignee: implementer
created: 2026-05-03
updated: 2026-05-05
---

# TASK-005: Bundle Dedicated Skills into Lifecycle Commands

## Design Context

- DESIGN-005: Bundle Dedicated Skills into Lifecycle Commands: seven command file edits, BundleRegistry, BUNDLE marker format, presence-marker table.

## Objective

Edit seven lifecycle command files to add dedicated skill invocations per the DESIGN-005 BundleRegistry. Add a test file that statically parses command files for required invocations. Add a pre-PR check to `scripts/validation/pre_pr.py` that blocks regressions.

---

## AC Traceability Matrix

| AC | Owning sub-task(s) | Notes |
|---|---|---|
| AC-1 (spec session-init) | T5-1 | Always-bundle; session-init skill owns missing-marker handling (Q2 resolution) |
| AC-2 (ship session-end + reflect) | T5-2 | session-end always-bundle; reflect with min-delta guard (5+ files) |
| AC-3 (plan pre-mortem) | T5-3 | Replaces inline analyst prompt at Step 6 |
| AC-4 (plan decision-critic) | T5-3 | Replaces inline critic prompt at Step 7 |
| AC-5 (build preflight chain) | T5-4 | context-gather -> steering-matcher -> conditional chestertons-fence |
| AC-6 (test Gate 3 threat-modeling) | T5-5 | Conditional on complexity tier >= 3 |
| AC-7 (test Gate 6 slo-designer + observability) | T5-5 | Always in Gate 6 |
| AC-8 (review doc-accuracy + chestertons-fence) | T5-6 | Axis 6 new; chestertons-fence conditional in Axis 1 |
| AC-9 (pr-review merge-resolver) | T5-7 | Presence-gated on `mergeable_state` |
| AC-10 (research context-gather) | T5-7 | Always preflight |
| AC-11 (BUNDLE marker) | T5-1 through T5-7 | Every sub-task adds BUNDLE lines |
| AC-12 (skipped:no-marker) | T5-1, T5-2, T5-4, T5-6, T5-7 | All presence-gated invocations |
| AC-13 (failed:reason warn-and-continue) | T5-1 through T5-7 | Every bundled invocation includes failure handling |
| AC-14 (pre_pr.py coverage check) | T5-8 | Single owner |

---

## Sub-Tasks

### T5-0: Prerequisite verification (skill existence) {#t5-0}

**Complexity**: S (< 1 hour)
**Commit tag**: n/a (verification only, no commit)
**Files affected** (0):

**In Scope**:
- Verify the 13 unique skills referenced in the BundleRegistry (15 total invocations) exist: `ls .claude/skills/{session-init,session-end,reflect,pre-mortem,decision-critic,context-gather,steering-matcher,chestertons-fence,threat-modeling,slo-designer,observability,doc-accuracy,merge-resolver}/SKILL.md`
- If any skill is missing, STOP and report. Do not proceed to T5-1.

**Out of Scope**: creating missing skills.

**Acceptance Criteria**:
- [ ] All 13 unique skill directories confirmed present.
- [ ] No errors from the listing command.

**Done when**: the `ls` command exits 0 for all 13 paths.

---

### T5-1: Edit spec.md (session-init preflight) {#t5-1}

**Complexity**: S (2-4 hours)
**Commit tag**: `feat(commands): bundle session-init into /spec preflight`
**Files affected** (1):

| File | Action | Description |
|---|---|---|
| `.claude/commands/spec.md` | modify | Add Step 0 presence-gated session-init before existing Step 1 |

**In Scope**:
- Insert Step 0 before "1. Clarify the problem" per DESIGN-005 spec.md diff.
- Always-bundle (no presence-check at the command layer; session-init skill owns its own missing-marker handling per Q2 resolution).
- BUNDLE marker: emit `BUNDLE: spec -> session-init (invoked)` on success, `BUNDLE: spec -> session-init (failed:<reason>)` on error.
- Step 0 is unnumbered or labeled 0 to avoid renumbering the existing flow.

**Out of Scope**: Changes to session-init skill internals.

**Acceptance Criteria**:
- [ ] `.claude/commands/spec.md` contains `Skill(skill="session-init")`.
- [ ] The invocation is unconditional (no presence-check at command layer; skill owns its own marker handling).
- [ ] `BUNDLE: spec -> session-init` appears in the file (as a comment or inline note).
- [ ] Existing Steps 1-9 are structurally unchanged (content, order, intent).

**Done when**: `grep -n 'session-init' .claude/commands/spec.md` returns at least one match containing `Skill(skill="session-init")`.

---

### T5-2: Edit ship.md (session-end + reflect postflight) {#t5-2}

**Complexity**: S (2-4 hours)
**Commit tag**: `feat(commands): bundle session-end and reflect into /ship postflight`
**Files affected** (1):

| File | Action | Description |
|---|---|---|
| `.claude/commands/ship.md` | modify | Add post-ship learnings step after Step 4 (Create PR) |

**In Scope**:
- Insert post-ship step between current Step 4 (Create PR) and Step 5 (Report) per DESIGN-005 ship.md diff.
- `session-end`: unconditional invocation (skill owns its own missing-marker handling per Q2 resolution).
- `reflect`: invoked when diff has 5 or more changed files; otherwise emit `BUNDLE: ship -> reflect (skipped:condition-not-met)`. Minimum-delta guard prevents noisy memory writes on trivial changes.
- BUNDLE markers for both skills, including failure path.
- Renumber "Report" to Step 6.

**Out of Scope**: Changes to session-end or reflect skill internals.

**Acceptance Criteria**:
- [ ] `.claude/commands/ship.md` contains `Skill(skill="session-end")` invoked unconditionally.
- [ ] `.claude/commands/ship.md` contains `Skill(skill="reflect")` with min-delta guard prose (5+ changed files).
- [ ] `BUNDLE: ship -> session-end` and `BUNDLE: ship -> reflect` appear in the file.
- [ ] Failure handling documented: both skills warn-and-continue.
- [ ] Pre-flight checks (Steps 1-3) unchanged.

**Done when**: Both `Skill(skill="session-end")` and `Skill(skill="reflect")` present in ship.md.

---

### T5-3: Edit plan.md (pre-mortem + decision-critic) {#t5-3}

**Complexity**: S (2-4 hours)
**Commit tag**: `feat(commands): replace inline analyst/critic prompts with skill invocations in /plan`
**Files affected** (1):

| File | Action | Description |
|---|---|---|
| `.claude/commands/plan.md` | modify | Replace Step 6 inline analyst pre-mortem and Step 7 inline critic with skill invocations |

**In Scope**:
- Replace Step 6 `Task(subagent_type="analyst"): You are a risk analyst. Run a pre-mortem...` with `Skill(skill="pre-mortem")` per DESIGN-005 plan.md diff.
- Replace Step 7 `Task(subagent_type="critic"): You are a plan reviewer. Validate...` with `Skill(skill="decision-critic")`.
- Both always-invoked (no presence gate).
- BUNDLE markers and failure handling for both.

**Out of Scope**: Steps 1-5 unchanged. Evaluation Axes and Principles sections unchanged.

**Acceptance Criteria**:
- [ ] `.claude/commands/plan.md` contains `Skill(skill="pre-mortem")` at Step 6.
- [ ] `.claude/commands/plan.md` contains `Skill(skill="decision-critic")` at Step 7.
- [ ] Former inline `Task(subagent_type="analyst")` pre-mortem prompt is removed from Step 6.
- [ ] Former inline `Task(subagent_type="critic")` reviewer prompt is removed from Step 7.
- [ ] `BUNDLE: plan -> pre-mortem` and `BUNDLE: plan -> decision-critic` appear in the file.
- [ ] Steps 1-5 content and order are unchanged.

**Done when**: `grep 'Skill(skill="pre-mortem")' .claude/commands/plan.md` and `grep 'Skill(skill="decision-critic")' .claude/commands/plan.md` both return matches, and the former inline `Task(subagent_type="analyst")` pre-mortem prompt is absent.

---

### T5-4: Edit build.md (context-gather + steering-matcher + conditional chestertons-fence preflight) {#t5-4}

**Complexity**: M (4-8 hours)
**Commit tag**: `feat(commands): add retrieval preflight chain to /build`
**Files affected** (1):

| File | Action | Description |
|---|---|---|
| `.claude/commands/build.md` | modify | Insert Preflight section before Complexity Assessment |

**In Scope**:
- Insert `## Preflight` section before existing `## Complexity Assessment` per DESIGN-005 build.md diff.
- Step 1: `Skill(skill="context-gather")` always.
- Step 2: `Skill(skill="steering-matcher")` always.
- Step 3: conditional `Skill(skill="chestertons-fence")`: check file age via `git log --format=%at -1 -- "<file>"` (paths MUST be quoted for CWE-78 prevention) for each file in scope. If any file's last commit is older than six months, invoke. Otherwise skip with `skipped:no-marker`.
- Each preflight skill has a 120-second timeout budget. On timeout: emit `BUNDLE: build -> <skill> (failed:timeout)` and continue.
- All three BUNDLE markers with failure handling.
- Presence-check commands MUST use literal file paths. MUST NOT interpolate `$ARGUMENTS` or user-supplied filenames directly into the shell condition without validation.

**Out of Scope**: Complexity Assessment and Agent sections unchanged. Guardrails unchanged.

**Acceptance Criteria**:
- [ ] `.claude/commands/build.md` contains `Skill(skill="context-gather")` in the Preflight section.
- [ ] `.claude/commands/build.md` contains `Skill(skill="steering-matcher")` in the Preflight section.
- [ ] `.claude/commands/build.md` contains `Skill(skill="chestertons-fence")` with conditional logic described.
- [ ] BUNDLE markers for all three skills present.
- [ ] No user input interpolated unsafely into shell presence check.
- [ ] Existing `## Complexity Assessment` and subsequent sections are structurally unchanged.

**Done when**: `grep -c 'Skill(skill=' .claude/commands/build.md` returns >= 3 (code-qualities-assessment + context-gather + steering-matcher + chestertons-fence = 4).

---

### T5-5: Edit test.md (threat-modeling at Gate 3; slo-designer + observability at Gate 6) {#t5-5}

**Complexity**: S (2-4 hours)
**Commit tag**: `feat(commands): bundle threat-modeling, slo-designer, observability into /test gates`
**Files affected** (1):

| File | Action | Description |
|---|---|---|
| `.claude/commands/test.md` | modify | Add conditional threat-modeling in Gate 3; add slo-designer and observability in Gate 6 |

**In Scope**:
- Gate 3: after `Skill(skill="security-scan")`, add conditional threat-modeling per DESIGN-005 test.md Gate-3 diff. Condition: complexity tier >= 3 (from Step 0 classification).
- Gate 6: before `Task(subagent_type="architect")`, add always-invoked slo-designer then observability per DESIGN-005 test.md Gate-6 diff.
- BUNDLE markers and failure handling for all three.

**Out of Scope**: Gates 1, 2, 4, 5 unchanged. Step 0 classification logic unchanged.

**Acceptance Criteria**:
- [ ] `.claude/commands/test.md` Gate 3 contains `Skill(skill="threat-modeling")` with tier-condition note.
- [ ] `.claude/commands/test.md` Gate 6 contains `Skill(skill="slo-designer")` and `Skill(skill="observability")`.
- [ ] `BUNDLE: test -> threat-modeling`, `BUNDLE: test -> slo-designer`, `BUNDLE: test -> observability` appear in the file.
- [ ] Existing gate 3 `security-scan` and architect invocations in Gate 6 are preserved.

**Done when**: `grep -c 'Skill(skill=' .claude/commands/test.md` returns the original count plus 3.

---

### T5-6: Edit review.md (doc-accuracy Axis 6; conditional chestertons-fence in Axis 1) {#t5-6}

**Complexity**: S (2-4 hours)
**Commit tag**: `feat(commands): add Axis 6 doc-accuracy and conditional chestertons-fence to /review`
**Files affected** (1):

| File | Action | Description |
|---|---|---|
| `.claude/commands/review.md` | modify | Add chestertons-fence conditional to Axis 1; add Axis 6 Documentation section; update synthesis step |

**In Scope**:
- Axis 1 (Architecture): append conditional `chestertons-fence` check at end of Axis 1 bullets per DESIGN-005 review.md Axis-1 diff.
- Axis 6 (Documentation): new `## Axis 6: Documentation` section invoking `doc-accuracy` always, before `## Principles`, per DESIGN-005 review.md Axis-6 diff.
- Step 8 synthesis: add `Documentation` row to the findings table.
- BUNDLE markers and failure handling for both skills.

**Out of Scope**: Axes 2-5 unchanged. Principles and Output sections unchanged except synthesis table row addition.

**Acceptance Criteria**:
- [ ] `.claude/commands/review.md` Axis 1 contains `Skill(skill="chestertons-fence")` with conditional note.
- [ ] `.claude/commands/review.md` contains `## Axis 6: Documentation` section with `Skill(skill="doc-accuracy")`.
- [ ] BUNDLE markers for both skills present.
- [ ] Synthesis step (Step 8) includes Documentation in its findings table.
- [ ] Axes 2-5 content is unchanged.

**Done when**: `grep -c 'Skill(skill=' .claude/commands/review.md` returns original count plus 2.

---

### T5-7: Edit pr-review.md (merge-resolver at Step 2) and research.md (context-gather preflight) {#t5-7}

**Complexity**: S (2-4 hours)
**Commit tag**: `feat(commands): bundle merge-resolver into /pr-review and context-gather into /research`
**Files affected** (2):

| File | Action | Description |
|---|---|---|
| `.claude/commands/pr-review.md` | modify | Add merge-resolver presence-gated invocation in Step 2 merge-eligibility check |
| `.claude/commands/research.md` | modify | Add context-gather always-invoked preflight before web fetches |

**In Scope**:

**pr-review.md**:
- In Step 2 "Check merge eligibility": run `gh pr view $PR --json mergeable -q '.mergeable'`. If result is `CONFLICTING`, invoke `Skill(skill="merge-resolver")` and emit `BUNDLE: pr-review -> merge-resolver (invoked)`. If not conflicting, emit `BUNDLE: pr-review -> merge-resolver (skipped:no-marker)`. If skill fails, emit `BUNDLE: pr-review -> merge-resolver (failed:<reason>)` and continue.

**research.md**:
- Add `## Preflight` section at top of process before any web fetch step per DESIGN-005 research.md diff. Invoke `Skill(skill="context-gather")` always. BUNDLE marker and failure handling.

**Out of Scope**: pr-review.md Steps 1, 3-6 unchanged. research.md memory-write steps unchanged.

**Acceptance Criteria**:
- [ ] `.claude/commands/pr-review.md` Step 2 contains `Skill(skill="merge-resolver")` with mergeable_state condition.
- [ ] `BUNDLE: pr-review -> merge-resolver` appears in pr-review.md.
- [ ] `.claude/commands/research.md` contains `Skill(skill="context-gather")` in a Preflight section.
- [ ] `BUNDLE: research -> context-gather` appears in research.md.
- [ ] BUNDLE failure-handling notes present in both files.

**Done when**: Both files contain their respective `Skill(skill="...")` invocations and BUNDLE markers.

---

### T5-8: Add test_command_bundles.py and pre_pr.py check {#t5-8}

**Complexity**: M (4-8 hours)
**Commit tag**: `test(commands): add static bundle coverage check for lifecycle commands`
**Files affected** (2):

| File | Action | Description |
|---|---|---|
| `tests/test_command_bundles.py` | create | Pytest test that parses each command file for required `Skill(skill="...")` calls from the BundleRegistry |
| `scripts/validation/pre_pr.py` | modify | Add a new check that runs the same parser and produces BLOCKING findings for missing invocations |

**In Scope**:

**test_command_bundles.py**:
- Read each command file in `.claude/commands/` as text.
- For each (command, skill) pair in the BundleRegistry (REQ-005), assert that `Skill(skill="<name>")` appears in the file.
- Parametrize by registry row so each assertion is an independent test case.
- No subprocess execution, no skill runtime invocation. Pure markdown parse.
- Follows pytest 8+ conventions.
- Coverage target: 80% (business logic per AGENTS.md floor).

**pre_pr.py check (advisory, per Q3 resolution)**:
- Add a new validation function `check_command_bundle_coverage()` that runs the same parse against the live command files.
- On any missing invocation, emit an **advisory WARN** finding (not BLOCKING) with: `file`, `expected_skill`, `ac_reference`. Drift is surfaced to reviewers; PR review is the enforcement layer (matches PR #1894 pattern for prose-driven changes).
- Function gated behind `BUNDLE_CHECK_ENFORCED` env var (default `0`, advisory). When set to `1`, findings escalate to BLOCKING — reserved for a future spec once the registry has stabilized.
- Integrate with existing `pre_pr.py` runner so it appears in the standard pre-PR output (under WARN category).
- Exit codes follow AGENTS.md contract: 0=ok regardless of advisory findings (env var `0`); 1=logic if env var is `1` and any bundle is missing.

**BundleRegistry (shared module, imported by both test and pre_pr)**:

Create `tests/bundle_registry.py` as the single source of truth:

```python
BUNDLE_REGISTRY = [
    ("spec.md",      "session-init"),
    ("ship.md",      "session-end"),
    ("ship.md",      "reflect"),
    ("plan.md",      "pre-mortem"),
    ("plan.md",      "decision-critic"),
    ("build.md",     "context-gather"),
    ("build.md",     "steering-matcher"),
    ("build.md",     "chestertons-fence"),
    ("test.md",      "threat-modeling"),
    ("test.md",      "slo-designer"),
    ("test.md",      "observability"),
    ("review.md",    "doc-accuracy"),
    ("review.md",    "chestertons-fence"),
    ("pr-review.md", "merge-resolver"),
    ("research.md",  "context-gather"),
]
```

Both `tests/test_command_bundles.py` and the new function in `scripts/validation/pre_pr.py` MUST import from `tests.bundle_registry` (or a shared path). Do NOT copy-paste the list into both files (prevents drift per pre-mortem finding #3).

**Out of Scope**: Runtime execution of skills. Testing skill behavior. The test is a static contract check only.

**Acceptance Criteria**:
- [ ] `tests/test_command_bundles.py` exists. Rows for not-yet-edited commands carry `@pytest.mark.xfail` so CI stays green during M1 (per plan §M1 Stays Green).
- [ ] Each test case names the command file and skill clearly in its ID (e.g., `test_bundle[spec.md-session-init]`).
- [ ] Running `pytest tests/test_command_bundles.py` exits 0 throughout (xfail counts as pass; M3 closing commit removes xfail marks).
- [ ] `scripts/validation/pre_pr.py` includes `check_command_bundle_coverage()`.
- [ ] Running `pre_pr.py` against a command file with a missing registry entry produces a WARN finding (not BLOCKING) when `BUNDLE_CHECK_ENFORCED=0` (default), and BLOCKING when `BUNDLE_CHECK_ENFORCED=1`.
- [ ] Running `pre_pr.py` against complete command files produces no findings related to bundles regardless of env var.
- [ ] New pre_pr.py function has a unit test in `tests/test_pre_pr.py` (or equivalent existing test file) covering: all-present (pass), one-missing under env=0 (WARN), one-missing under env=1 (BLOCKING), empty-registry (pass).
- [ ] Python style and exit code contract match existing `pre_pr.py` conventions.

**Done when**: `pytest tests/test_command_bundles.py` exits 0 (xfails as designed during M1; un-xfailed rows pass), `python3 scripts/validation/pre_pr.py` produces no BLOCKING issues with `BUNDLE_CHECK_ENFORCED=0` (default; advisory WARN findings are expected during M1/M2), and the CWE-78 path-quoting test passes (verifies all `git log` commands in build.md and review.md quote file paths).

---

## Sequencing and Dependencies

```
T5-0 (prerequisite verification)
  -> T5-1 (spec.md)        \
     T5-2 (ship.md)         \
     T5-3 (plan.md)          > independent; can run in parallel after T5-0
     T5-4 (build.md)        /
     T5-5 (test.md)        /
     T5-6 (review.md)     /
     T5-7 (pr-review.md + research.md)
       -> T5-8 (test + pre_pr.py + shared registry)   [depends on T5-1 through T5-7 complete]
```

T5-1 through T5-7 are independent of each other. T5-8 depends on all seven command edits being complete because it validates the full registry.

---

## Commit Budget (AGENTS.md: <= 5 files, <= 20 commits/PR)

| Sub-task | Commits | Files |
|---|---|---|
| T5-0 | 0 | 0 (verification only) |
| T5-1 | 1 | 1 |
| T5-2 | 1 | 1 |
| T5-3 | 1 | 1 |
| T5-4 | 1 | 1 |
| T5-5 | 1 | 1 |
| T5-6 | 1 | 1 |
| T5-7 | 1 | 2 |
| T5-8 | 1 | 3 |
| **Total** | **8 commits** | **11 files** |

All within AGENTS.md limits (8 commits < 20; largest commit is 3 files < 5).

---

## Estimated Effort

| Sub-task | Size | Hours |
|---|---|---|
| T5-1 | S | 2-3 |
| T5-2 | S | 2-3 |
| T5-3 | S | 2-3 |
| T5-4 | M | 4-5 |
| T5-5 | S | 2-3 |
| T5-6 | S | 2-3 |
| T5-7 | S | 2-3 |
| T5-8 | M | 4-6 |
| **Total** | | **20-29 hours** |

---

## Testing Requirements

- `tests/test_command_bundles.py`: pure static parse; no subprocess, no skill execution; pytest 8+.
- Coverage: 80% business logic per AGENTS.md (the parser function is the business logic).
- `tests/test_pre_pr.py` (or existing): three new parametrized test cases for `check_command_bundle_coverage()`.
- No test mocks network or file system writes; all reads are against the actual command files under `.claude/commands/`.

---

## Files Affected (Summary)

| File | Task | Action |
|---|---|---|
| `.claude/commands/spec.md` | T5-1 | modify |
| `.claude/commands/ship.md` | T5-2 | modify |
| `.claude/commands/plan.md` | T5-3 | modify |
| `.claude/commands/build.md` | T5-4 | modify |
| `.claude/commands/test.md` | T5-5 | modify |
| `.claude/commands/review.md` | T5-6 | modify |
| `.claude/commands/pr-review.md` | T5-7 | modify |
| `.claude/commands/research.md` | T5-7 | modify |
| `tests/bundle_registry.py` | T5-8 | create |
| `tests/test_command_bundles.py` | T5-8 | create |
| `scripts/validation/pre_pr.py` | T5-8 | modify |

---

## Related Documents

- Requirements: `.agents/specs/requirements/REQ-005-command-skill-bundling.md`
- Design: `.agents/specs/design/DESIGN-005-command-skill-bundling.md`
- Analysis: `.agents/analysis/command-skill-bundling-2026-05-03.md`
