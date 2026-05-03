# Execution Plan: Agent Eval Harness Spike (#1854)

## Metadata

| Field | Value |
|-------|-------|
| **Status** | In Progress |
| **Created** | 2026-05-03 |
| **Owner** | implementer |
| **Complexity** | Medium |
| **Spec** | REQ-004 / DESIGN-004 / TASK-004 |
| **Issue** | #1854 |
| **Spec PR** | #1870 (draft) |

## Objectives

- [ ] **MS-1**: Scaffolding ready for offline use (corpus + dry-run runs without API)
- [ ] **MS-2**: Runner produces verifiable JSONL output and full report on real calls
- [ ] **MS-3**: Decision recorded, ADR merged, recommendation ratified by architect-tier review
- [ ] All 10 acceptance criteria from REQ-004 verified pass/fail
- [ ] Spike committed under `evals/security-spike/` per OQ-2
- [ ] ADR landed at `.agents/architecture/ADR-NNN-agent-eval-discipline.md`

---

## Milestones

### MS-1 — Scaffolding ready for offline use

**Member sub-tasks**: T4-1 (scaffolding + scoring + plan runner + dry-run), T4-4 (corpus build, 3 commits)

**Exit criteria** (all binary pass/fail):

- `--dry-run` against the 10-fixture corpus exits 0 and prints exactly 60 planned calls plus a USD cost estimate with `rate_as_of` date
- All 10 fixtures pass `FixtureValidator` with zero errors; provenance ∈ `{synthetic, paraphrased-from-public}`
- ≥3 fixtures per verdict class (`IDENTIFY`, `OK`, `ESCALATE`); ≥3 explicitly **agent-discriminating** fixtures with rationale in `fixtures/README.md`
- `ScoringEngine`, `FixtureValidator`, `PlanRunner` unit tests pass; one test asserts `schemaVersion: 2` raises `SchemaVersionError`
- No real API call made anywhere in the test suite (mocked at `AnthropicAPIAdapter` boundary)

**Independence claim**: Ships as a standalone PR. The scaffolding, fixture schema, corpus, and dry-run CLI are useful without any live model call — corpus reviewers can audit fixtures, and the schema contract is locked.

**Reversibility**: LOW cost. No run data written. New top-level `evals/` directory is easily deleted. No changes to existing `scripts/eval/` logic — only additions and one module-private edit to `_plan_runner.py`.

**Approximate share of total effort**: T4-1 (3h) + T4-4 (6h) ≈ **30%** of total.

**Parallel opportunities**: T4-1 and T4-4 run concurrently once T4-1 lands the fixture schema. T4-4 must split into three commits (T4-4a/b/c) per AGENTS.md ≤5-file rule.

---

### MS-2 — Runner produces verifiable JSONL output

**Member sub-tasks**: T4-2 (runner + retry + idempotency), T4-3 (reporting: recall, bootstrap CI, distribution, flakiness)

**Exit criteria**:

- Running against the full corpus produces exactly 60 records in `runs.jsonl`
- `report.json` and `REPORT.md` present with all required fields and `schemaVersion: 1`
- `recall_with_errors` and `recall_excluding_errors` both present; bootstrap CI bounds non-empty numeric
- `recommendation` field present (may be `null` at this milestone; finalized in MS-3)
- `DuplicateRunError` test passes; adapter retry tests pass on 408/429/5xx/timeout; non-transient 4xx records `outcome=error` immediately
- `ANTHROPIC_API_KEY` absent from all log lines (asserted in test)
- Error rate > 10% triggers exit code 1 (tested with mocked failures)

**Independence claim**: Ships as a PR layered on MS-1. Delivers a fully operational offline eval loop — anyone can re-run the spike and reproduce the same JSONL given the same prompt and fixture SHAs. The report renders a complete numeric picture before any human decision is made.

**Reversibility**: MEDIUM. Introduces live Anthropic API usage. Run directories are timestamped + UUID, so rollback is trivial. Runner code is additive; no existing file is broken. The `recommendation: null` choice keeps the report structurally valid until MS-3 finalizes the verdict.

**Approximate share of total effort**: T4-2 (6h) + T4-3 (6h) ≈ **40%** of total.

**Parallel opportunities**: T4-2 and T4-3 can run concurrently against synthetic `RunRecord` fixtures (T4-1 defines the type). T4-3's *integration* AC ("REPORT.md contains per-fixture breakdown") can only be confirmed after T4-4 and the live run, so the parallel claim applies to **unit-test development**, not integration validation.

---

### MS-3 — Decision and methodology locked

**Member sub-tasks**: T4-5 (execute spike), T4-6 (write ADR + reserve number), T4-7 (decision)

**Exit criteria**:

- `runs.jsonl` committed (60 records, no API key present, baseline_prompt_sha and agent_prompt_sha recorded)
- ADR exists at `.agents/architecture/ADR-NNN-agent-eval-discipline.md`, passes `pre_pr.py`, frontmatter status: proposed
- ADR contains all required sections: scope (deterministic-scorable agents only), held-out definition, scoring discipline, baseline (deliberately naive), threshold methodology with worked example, CI cost projection, decision owner + scrap-consequence, cadence, ADR-057 cross-reference, advice-quality acknowledgment, survivorship-bias acknowledgment
- Baseline prompt SHA in ADR matches `baseline_prompt_sha` in `report.json`
- `recommendation` field set to one of `{graduate-to-CI, keep-as-audit, scrap}` per AC-5 decision criteria
- ≥2 cited evidence pieces in `REPORT.md` recommendation section
- PR ratified by architect-tier reviewer (Tier 3) before merge

**Independence claim**: Depends on MS-2. The spike report and ADR are the deliverable the architect ratifies.

**Reversibility**: HIGH cost on `graduate-to-CI`. The ADR is effectively one-way once merged (supersession requires a follow-on ADR). Run data is immutable by design. The `scrap` path is documented and recoverable: archive `evals/security-spike/` AND the runner code in `scripts/eval/eval-agent-vs-baseline.py` plus the six new modules to `evals/_archive/security-spike-<RUN_ID>/scripts/`.

**Approximate share of total effort**: T4-5 (3h) + T4-6 (6h) + T4-7 (3h) ≈ **30%** of total. T4-7 sized S (not XS) because the decision narrative — applying AC-5 criteria, citing evidence, defending to architect review — is the actual work.

**Parallel opportunities**: T4-6 ADR draft can begin while T4-5 is executing (~2 minutes of API calls), since the ADR structure is known. T4-7 is blocked on both T4-5 and T4-6 completion.

---

## Dependency Graph

```
MS-1                          MS-2                          MS-3
 │                              │                              │
 ├── T4-1 ────┐                 │                              │
 │            ├──────────┬──────┤                              │
 ├── T4-4a ───┘          │      ├── T4-2 ──────┐              │
 ├── T4-4b ──────────────┤      │              ├── T4-5 ──┐    │
 └── T4-4c ──────────────┘      ├── T4-3 ──────┘          │    │
                                                          ├──── T4-6 ── T4-7
                                              (T4-6 draft starts in
                                               parallel with T4-5)
```

Critical path: T4-1 → T4-2 → T4-3 → T4-5 → T4-6 → T4-7 (~27 h sequential at the higher end of estimates).

---

## Risk Register

Sorted by `Likelihood × Impact` descending. P0 = blocks ship; P1 = high pain but workable; P2 = nuisance.

| # | Risk | Likelihood | Impact | Priority | Mitigation | Owner |
|---|------|------------|--------|----------|------------|-------|
| R1 | Agent-discriminating fixtures look discriminating but aren't — naive baseline passes them, producing a false null delta and a misleading verdict | HIGH | HIGH | **P0** | Add T4-4 pre-flight gate: run a single fixture through both variants live before committing the full corpus. Confirm baseline recall < 0.70 on the agent-discriminating subset. Write rationale into `fixtures/README.md` for each agent-discriminating fixture | T4-4 |
| R2 | `aggregate_multi_run_scores` reuse contradiction propagates and the implementer averages binary recall as floats | MEDIUM | HIGH | **P0** | TASK-004 and DESIGN-004 now explicitly state "Do NOT reuse"; cross-reference table fixed; verified by reading `_eval_common.py:19-39`. Resolved at plan time | T4-3 |
| R3 | Pricing constants missing from any module → AC-8 cost-line format check fails on T4-1 | HIGH | MEDIUM | **P1** | TASK-004 T4-1 now scopes the pricing constants as module-private inside `_plan_runner.py` with a hardcoded `rate_as_of` date. Resolved at plan time | T4-1 |
| R4 | Flakiness false-positive at temperature=0 halts the spike at T4-5 with no report | MEDIUM | HIGH | **P1** | If `flakiness=true` on first run, T4-5 contingency: re-run N=5; if variance persists for the same fixture on ≥2 of 5 reps, mark that fixture `flaky=true` in JSON and exclude from delta with documented note. AC-10 allows fixture-level exclusion with documentation | T4-5 |
| R5 | T4-4 commit budget violated (12 files, ≤5 cap) | HIGH | LOW | **P1** | T4-4 now mandates 3 commits (T4-4a/b/c) per AGENTS.md; total commit count updated to 9. Resolved at plan time | T4-4 |
| R6 | Anthropic API rate limit during T4-5 60-call live run; partial failure with no resume path | LOW | MEDIUM | **P2** | Add `--resume <RUN_ID>` flag to runner that skips completed `(fixture, variant, run_index)` triples instead of raising `DuplicateRunError`. Pre-flight: verify API tier supports 60 sequential calls per session before T4-5 | T4-2 (resume), T4-5 (pre-flight) |
| R7 | ADR number collision with concurrent ADR PRs | MEDIUM | LOW | **P2** | T4-6 reserves the next ADR number at task start by claiming the file with frontmatter only, body filled afterward. Resolved at plan time | T4-6 |
| R8 | T4-7 sized XS underinvests the decision narrative; PR fails architect review | HIGH | MEDIUM | **P1** | T4-7 resized to S; explicit note that decision prose is the work, not the field write. Resolved at plan time | T4-7 |
| R9 | Architect review SLA undefined; PR sits in limbo after T4-6 merges | LOW | LOW | **P2** | If no architect-tier review within 5 business days, default `recommendation` to `keep-as-audit` with note "pending review" — does not graduate to CI without review, does not scrap prematurely | T4-7 |
| R10 | `scrap` verdict leaves runner code in `scripts/eval/` (lint, type-check, coverage burden for dead code) | LOW | MEDIUM | **P2** | T4-7 scope addendum: on `scrap`, move runner + 6 modules + test file to `evals/_archive/security-spike-<RUN_ID>/scripts/`; ADR `status: superseded`. Already in TASK-004 | T4-7 |
| R11 | T4-5 commits structurally invalid `recommendation: null` | MEDIUM | LOW | **P2** | DESIGN-004 schema now permits `null` on initial T4-5 commit; T4-7 finalizes. Resolved at plan time | T4-3, T4-5 |
| R12 | Hidden coupling to ongoing security-scan / ADR-057 work on main | LOW | LOW | **P2** | Spike branch is short-lived; rebase before T4-5 to surface conflicts early. No code overlap expected | implementer |

### P0 risk summary

Two P0 risks remain at start-of-execution:

1. **R1** (corpus quality) — must be resolved during T4-4 with the pilot gate
2. **R2** (`aggregate_multi_run_scores`) — already mitigated at plan time via TASK-004 + DESIGN-004 fixes

---

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-05-03 | Group T4-1..T4-7 into 3 milestones (MS-1: scaffolding+corpus, MS-2: runner+report, MS-3: decision+ADR) | Each milestone is independently shippable and produces user-visible value or de-risks the next. Aligns with the spike's natural decision points. | Single big-bang PR (rejected: too large, no incremental sign-off). 7 PRs (rejected: review fatigue, no logical grouping) |
| 2026-05-03 | T4-4 splits into 3 commits (T4-4a/b/c) | AGENTS.md hard cap ≤5 files per commit; 12 fixture files cannot fit in 2 commits | Bypass rule with audit reason (rejected: rule exists for review-load reasons; not a one-off case) |
| 2026-05-03 | T4-7 resized XS → S | Decision narrative + architect review prep is consistently underestimated | Keep XS, hope it's enough (rejected: critic finding F2) |
| 2026-05-03 | Pricing constants stay module-private in `_plan_runner.py` for the spike | Keeps T4-1 within 5-file budget; promotion to `_eval_common.py` happens later if needed | Add a 6th file to T4-1 (rejected: budget) or split T4-1 into T4-0+T4-1 (rejected: spawns extra PR for tiny content) |
| 2026-05-03 | `recommendation: null` is permitted at T4-5; T4-7 finalizes | Avoids merging T4-5+T4-7 into one commit (which would violate three-commit-per-PR convention for the spike PR shape); schema gets a documented nullable | Merge T4-5+T4-7 (rejected: blurs decision audit trail) |
| 2026-05-03 | ADR number reserved at start of T4-6, not earlier | Reservation in T4-1 would burn a file budget slot; the spike's branch is short enough that collision risk in T4-6 is acceptable | Reserve in T4-1 (rejected: budget pressure) |
| 2026-05-03 | Do NOT reuse `aggregate_multi_run_scores`; new module-private helper instead | Existing function averages dimensional LLM-judge scores; binary pass/fail recall has different shape (verified at `_eval_common.py:19-39`) | Adapt the function (rejected: changes its semantics for ADR-057 callers) |

---

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-05-03 | Created plan from REQ-004 / DESIGN-004 / TASK-004; ran milestone-planner + analyst pre-mortem + critic plan review in parallel; resolved 5 plan-level findings (T4-4 commit budget, `aggregate_multi_run_scores` contradiction, T4-7 size, recommendation: null schema, ADR number reservation) | claude (Opus 4.7) |

---

## Blockers

None. Plan is shippable with mitigations in place. P0 risk R1 (corpus quality) requires execution-time vigilance during T4-4; P0 risk R2 is resolved at plan time.

---

## Deferred Items (out of scope for this plan)

- Multi-agent eval coverage (qa, analyst, etc.) — requires the methodology ADR (T4-6) to land first
- CI gate for the spike runner — gated by T4-7 graduate-to-CI verdict
- Cross-model variance study (Sonnet/Opus/Haiku matrix) — single-model spike only
- Held-out corpus expansion to N≥30 — graduate-to-CI prerequisite per ADR cadence section
- LLM-as-judge advice-quality eval as a gated signal — explicitly rejected; permitted only as advisory sidecar
- Conflation with ADR-057 prompt-change validation — different question, no merge
- Workaround eval per #1868 (skill 1M-context bug) — separate work item, but shares the eval pattern designed here

---

## Related

- Issue: #1854 (`spike: prove the eval-harness shape with one agent + write the ADR`)
- Spec PR: #1870 (draft, in review)
- Cross-references ADR-057 (prompt-change before/after — different question)
- Surfaced workaround issue: #1868 (skill subprocess + 1M context bug)
- Upstream: anthropics/claude-code#55694
