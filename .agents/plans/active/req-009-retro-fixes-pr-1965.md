# Execution Plan: REQ-009 Retro Fixes from PR #1965

## Metadata

| Field | Value |
|-------|-------|
| **Status** | In Progress |
| **Created** | 2026-05-10 |
| **Owner** | richard (with Claude Opus 4.7 1M context) |
| **Complexity** | Medium (Tier 2-3, ~11h) |

## Objectives

Five milestones derived from `.agents/retrospective/2026-05-10-pr-1965-review-axes-convergence.md` after critic NEEDS-REVISION pass on the initial 4-milestone draft.

- [ ] **M1: Stable-zero wrapper (hardened)** — `.claude/skills/github/scripts/pr/wait_for_unresolved_zero.py`. Polls existing pagination-correct script; requires 3 consecutive zero readings ≥180s apart (not 2x60s); argv-vector subprocess call (CWE-78); integration test with real-pagination fixture.
- [ ] **M2: applyTo glob extension (repriced)** — `.claude/rules/canonical-source-mirror.md` extends glob to cover `.claude/review-axes/**` and `.github/prompts/**`. Contract test handles string-vs-list applyTo coercion via fnmatch.
- [ ] **M3: Co-change-checklist (auto-detect + opt-in)** — `.claude/commands/spec.md` Step 6 emits checklist on (a) proposer-flagged multi-site change OR (b) auto-detected token literal patterns in diff scope.
- [ ] **M4: Rework warning (calibrated)** — `.claude/skills/session-end/scripts/complete_session_log.py` emits warning for files edited 6+ times. Includes `--diff-filter=R` rename detection, excludes generated patterns (`*.session.json`, `src/claude/`).
- [ ] **M5: Bot-cascade pre-push warning (NEW)** — `.githooks/pre-push` warns (not blocks) when current PR has unresolved bot threads or recent bot reviews. Closes the retro's highest-leverage gap (~20 commits saved).

## Milestones

### M1: Stable-zero wrapper (hardened)

**Purpose.** Detect bots opening threads between agent queries. Closes the PR #1965 "0 unresolved" lie at the source.

**Tasks (atomic, S/M/L):**
- T1.1 (M, ~1.5h): create `wait_for_unresolved_zero.py` with argv-vector subprocess call, 180s default interval, 3-reading default, CLI flags per ADR-035 exit codes
- T1.2 (M, ~1h): unit tests (subprocess.run stub) for bot-settle scenario `[0, 3, 0, 0]` requiring reading 4
- T1.3 (S, ~0.5h): integration test against multi-page GraphQL fixture (real pagination, not stubbed subprocess)
- T1.4 (S, ~0.5h): test for `fetched_pages_complete=false` rejection on first zero reading
- T1.5 (S, ~0.5h): test for max-wait timeout exits 1 with `settled=false`

**Exit criteria:**
- [ ] Script exists under `.claude/skills/github/scripts/pr/`
- [ ] All 4 tests pass
- [ ] Subprocess call uses argv-vector (`shell=False`)
- [ ] Pagination fixture proves wrapper rejects `fetched_pages_complete=false`

**Acceptance criteria mapped:** REQ-009-01, REQ-009-02 (revised to 180s interval + 3 readings)
**Estimated commits:** 4
**Hours:** ~3.5h
**Dependencies:** none. Parallel with M2-M5.

### M2: applyTo glob extension (repriced)

**Purpose.** Bring `.claude/review-axes/**` and `.github/prompts/**` under the canonical-source-mirror rule that PR #1887 retro proposed.

**Tasks:**
- T2.1 (S, ~15m): edit frontmatter `applyTo` value in `.claude/rules/canonical-source-mirror.md`
- T2.2 (M, ~45m): create `tests/build_scripts/test_canonical_source_mirror.py` with string-vs-list applyTo coercion via fnmatch; assert glob matches both new file paths
- T2.3 (S, ~15m): rule body amendment to clarify the glob now covers prompt files

**Exit criteria:**
- [ ] Frontmatter updated
- [ ] Test passes for both string and list shapes of applyTo
- [ ] Test asserts `.claude/review-axes/analyst.md` matches AND `.github/prompts/pr-quality-gate-analyst.md` matches

**Acceptance criteria mapped:** REQ-009-03
**Estimated commits:** 2
**Hours:** ~1.25h
**Dependencies:** none. Parallel with M1, M3-M5.

### M3: Co-change-checklist (auto-detect + opt-in)

**Purpose.** Surface multi-site contract changes at spec time so verdict-token-style cascades don't recur. Auto-detect closes the "proposer in a hurry says no" bypass.

**Tasks:**
- T3.1 (M, ~45m): write `## Co-change checklist` section template in `.claude/commands/spec.md` Step 6 region
- T3.2 (M, ~30m): file-pattern auto-detect: if PRD touches `scripts/validation/**` AND `.claude/hooks/**` simultaneously, OR if Q4 mentions a token literal (regex pattern, enum value, status code), emit checklist automatically
- T3.3 (S, ~15m): structural grep test confirming Step 6 has the section template

**Exit criteria:**
- [ ] Step 6 region in spec.md contains `## Co-change checklist` template
- [ ] Auto-detect rule documented in spec.md (not enforced in code; documentation only at this milestone)
- [ ] Structural test asserts template presence

**Acceptance criteria mapped:** REQ-009-04, REQ-009-05
**Estimated commits:** 2
**Hours:** ~1.5h
**Dependencies:** none. Parallel with M1, M2, M4, M5.

### M4: Rework warning (calibrated)

**Purpose.** Surface 56-edit-`scan.py`-class loops before submission. Calibrated against PR #1965 actual edit cycles.

**Tasks:**
- T4.1 (M, ~1h): extend `complete_session_log.py` to walk `git log --name-only --diff-filter=R` against branch base, count per-file edits collapsing renames, exclude `*.session.json` + `src/claude/` generated patterns
- T4.2 (M, ~45m): test `tests/skills/session-end/test_rework_warning.py` against stubbed git log fixtures (one file at 6 edits, one at 3, one renamed mid-branch)
- T4.3 (S, ~15m): emit `rework-warning: none` line on no warnings (per REQ-009-08)
- T4.4 (S, ~30m): document threshold-6 as starter calibration with 30-invocation kill-criteria review (mirrors Step 0 gate kill criteria)

**Exit criteria:**
- [ ] Script extension produces warning lines for 6+ edit files
- [ ] Rename detection collapses split filenames before counting
- [ ] Generated-pattern exclusion verified by test
- [ ] `rework-warning: none` emitted when threshold not crossed

**Acceptance criteria mapped:** REQ-009-07, REQ-009-08, REQ-009-09
**Estimated commits:** 3
**Hours:** ~2.5h
**Dependencies:** none. Parallel with M1-M3, M5.

### M5: Bot-cascade pre-push warning (NEW)

**Purpose.** Highest-leverage retro fix (~20 commits saved). Warn before push when bots have open threads on the current PR or are mid-scan.

**Tasks:**
- T5.1 (M, ~1h): extend `.githooks/pre-push` Phase 5c to query `get_unresolved_review_threads.py` for current branch's PR (if PR exists) and warn if `unresolved_count > 0` OR last bot review is <120s old
- T5.2 (S, ~30m): test `tests/hooks/test_bot_cascade_warning.py` with stubbed PR context (existing PR + open thread, no PR, fresh-bot-review scenarios)
- T5.3 (S, ~30m): document opt-out via `--no-verify` (existing) and recommend batch-fix pattern in hook output

**Exit criteria:**
- [ ] Hook warns (does NOT block) on open bot threads or recent bot review
- [ ] Test covers 3 scenarios: open threads, no PR, fresh bot review
- [ ] Hook output references the batch-fix pattern documented in pr-review-observations.md Session 14

**Acceptance criteria mapped:** new REQ-009-10, REQ-009-11 (to be added to REQ-009 doc during /build)
**Estimated commits:** 2
**Hours:** ~2h
**Dependencies:** none. Parallel with M1-M4.

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-05-10 | Add M5 (bot-cascade pre-push warning) | Retro names this as highest-leverage fix (~20 commits saved). Originally omitted from /spec scope. Critic flagged silent omission. | Defer to separate /spec; reject because retro evidence is concrete and the fix is small. |
| 2026-05-10 | M1 interval 180s + 3 readings, not 60s + 2 | Pre-mortem found 60s too short for Copilot/Devin webhook latency (30-120s). 3x180s = 9min ceiling but actual settle time is shorter in normal operation. | 60s + 2 readings (rejected: failure class same as PR #1965); webhook-receipt-based wait (rejected: no GitHub API surface). |
| 2026-05-10 | M3 auto-detect documented but not enforced | Documentation-only at this milestone keeps wedge tight. Enforcement is a follow-up after one /spec invocation uses the auto-detect rule. | Implement enforcement now (rejected: wedge creep, +1.5h, low ROI); skip auto-detect entirely (rejected: weakens M3 to opt-in only, critic flagged). |
| 2026-05-10 | M4 threshold-6 starter, kill criteria at 30 invocations | Critic flagged 6 as arbitrary. Threshold tuning needs data; kill-criteria pattern from Step 0 gate proven on PR #1931. | Calibrate from PR #1965 data first (rejected: requires git archaeology overhead, not in scope); skip threshold (rejected: warning needs a trigger). |
| 2026-05-10 | Skip CVA | Tier 2-3 with single use case per fix. CVA matrix would be 5x1 (no commonality). | Run CVA anyway (rejected: ceremony with no signal). |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-05-10 | Plan created from REQ-009 + critic NEEDS-REVISION pass | Claude Opus 4.7 (1M context) |

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| M1 timing assumption wrong (3x180s still misses bot scans) | MED | HIGH | M5 covers the residual gap (warns at push time, before bots even start). Combined M1+M5 reduces single-point-of-failure. |
| M1 subprocess.run stub doesn't exercise real pagination | MED | HIGH | T1.3 integration test against multi-page GraphQL fixture pins real pagination contract. |
| M2 applyTo glob breadth causes review noise on unrelated edits | MED | LOW | Rule body already requires "match"/"mirror" claim keywords in docstring. Edits without those keywords don't trigger. |
| M3 auto-detect false negatives (token literal not detected) | MED | LOW | Documentation-only this milestone; first failure becomes data for enforcement design. |
| M4 threshold-6 false positives on TDD iteration | MED | MED | Kill criteria at 30 invocations. Rename detection + generated-pattern exclusion handle the obvious cases. |
| M5 hook noise (warns on every push) | LOW | LOW | Warn-only (not block). Opt-out via `--no-verify` already exists. Threshold = unresolved_count > 0 (skips clean PRs). |
| 5 PRs entering review same day = 20 bot scans, cross-PR thread storm | MED | MED | Stage merges 24h apart per pre-mortem C7. M2 first (lowest surface), then M5, then M4, then M3, then M1 (largest surface). |
| CWE-78 in M1 subprocess call | LOW | HIGH | T1.1 explicitly requires argv-vector with `shell=False`. Test asserts no string concatenation. |

## Blockers

- None.

## Deferred items

| Item | Reason | Future trigger |
|------|--------|----------------|
| M3 auto-detect enforcement (code-level) | Wedge creep; needs one cycle of usage data | After 5 /spec invocations use the manual auto-detect rule |
| Pagination contract tests for sibling scripts (`get_pr_review_threads.py`, `get_pr_checks.py`) | Pattern from M1 mechanical to replicate | Future PR after M1 ships |
| Threshold tuning for M4 rework warning | Requires 30+ session-end invocations of data | Kill-criteria review at 30 invocations |
| Per-extension thresholds for M4 (test files higher, generated lower) | Adds complexity without baseline data | After threshold-6 calibration shows skew |
| Error budget gating in CI (859 unresolved errors per context-mode insights) | Tier 3+ cross-team policy work | Separate /spec invocation |
| Agent tool-call rejection logging (77 rejected Agent calls) | Different surface (Claude Code harness, not repo) | Separate /spec; coordinate with Anthropic Claude Code |
| P95 latency profiling (109s) | Requires telemetry infra | Separate /spec |
| **Class 3: tool-name + JSON-shape hallucination** | Different failure class (FM-1 Context Reading per retro). Agent guesses script names (`get_unresolved_threads.py` vs `get_unresolved_review_threads.py`) and JSON shapes (`Data` wrapper not always present). Same root cause as 77 rejected Agent calls + 56 edits to scan.py. | Separate /spec invocation; user-routed 2026-05-10. |

## Related

- Source spec: `.agents/specs/requirements/REQ-009-retro-fixes-pr-1965.md`
- Source design: `.agents/specs/design/DESIGN-009-retro-fixes-pr-1965.md`
- Source tasks: `.agents/specs/tasks/TASK-009-retro-fixes-pr-1965.md`
- Retrospective: `.agents/retrospective/2026-05-10-pr-1965-review-axes-convergence.md`
- Predecessor retro: `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md` (canonical-source-mirror rule origin)
- Memory: `.serena/memories/pr-review/pr-review-observations.md` Session 15 entries (HIGH-confidence learnings encoded 2026-05-10)
