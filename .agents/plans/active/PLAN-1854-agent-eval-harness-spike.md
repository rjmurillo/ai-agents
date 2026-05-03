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
MS-1                                    MS-2                          MS-3
 │                                        │                              │
 │  T4-1 ──────────────────┐               │                              │
 │  (scaffolding + types)  │               │                              │
 │                         ├───────────────┤                              │
 │  T4-4a ─> T4-4b ─> T4-4c (3 commits)    │                              │
 │  (corpus, mandatory                    │                              │
 │   sequential split per                  ├── T4-2 ──────┐              │
 │   AGENTS.md ≤5 files)                   │   (runner)    │              │
 │                                         │               ├── T4-5 ──┐   │
 │                                         ├── T4-3 ───────┘ (live)   │   │
 │                                         │   (report)               │   │
 │                                                                    ├── T4-6 ── T4-7
 │                                              (T4-6 ADR draft starts in
 │                                               parallel with T4-5 live run)
 │                                              (T4-7 = 1 commit usually,
 │                                               up to 4 commits if scrap-path)
```

Within MS-1, T4-1 and T4-4a may begin in parallel once T4-1 lands the fixture schema (`_eval_agent_types.py`). T4-4a/b/c are sequential within T4-4. Within MS-2, T4-2 and T4-3 develop in parallel against T4-1's `RunRecord` type with synthetic test records; integration validation gates on T4-4 corpus.

Critical path: T4-1 → T4-2 → T4-3 → T4-5 → T4-6 → T4-7 (~27 h sequential at the higher end of estimates).

---

## Risk Register

Sorted by `Likelihood × Impact` descending. P0 = blocks ship; P1 = high pain but workable; P2 = nuisance.

| # | Risk | Likelihood | Impact | Priority | Mitigation | Owner |
|---|------|------------|--------|----------|------------|-------|
| R1 | Agent-discriminating fixtures look discriminating but aren't — naive baseline passes them, producing a false null delta and a misleading verdict | HIGH | HIGH | **P0** | Add T4-4 pre-flight gate: run a single fixture through both variants live before committing the full corpus. Confirm baseline recall < 0.70 on the agent-discriminating subset. Write rationale into `fixtures/README.md` for each agent-discriminating fixture | T4-4 |
| R2 | `aggregate_multi_run_scores` reuse contradiction propagates and the implementer averages binary recall as floats | MEDIUM | HIGH | **P0** | TASK-004 and DESIGN-004 now explicitly state "Do NOT reuse"; cross-reference table fixed; verified by reading `_eval_common.py:19-39`. Resolved at plan time | T4-3 |
| R3 | Pricing constants missing from any module → AC-8 cost-line format check fails on T4-1 | HIGH | MEDIUM | **P1** | Pricing constants `MODEL_PRICING_RATES_USD_PER_1K_TOKENS` and `PRICING_RATE_AS_OF` are module-public in `_eval_common.py` (added in T4-1). Both `_plan_runner.py` and `_report_aggregator.py` import from this single owner. Single source of truth; no peer-import. Resolved at plan time. | T4-1 |
| R4 | Flakiness false-positive at temperature=0 halts the spike at T4-5 with no report | MEDIUM | HIGH | **P1** | If `flakiness=true` on first run, T4-5 contingency: re-run N=5; if variance persists for the same fixture on ≥2 of 5 reps, mark that fixture `flaky=true` in JSON and exclude from delta with documented note. AC-10 allows fixture-level exclusion with documentation | T4-5 |
| R5 | T4-4 commit budget violated (12 files, ≤5 cap) | HIGH | LOW | **P1** | T4-4 now mandates 3 commits (T4-4a/b/c) per AGENTS.md; total commit count updated to 9. Resolved at plan time | T4-4 |
| R6 | Anthropic API rate limit during T4-5 60-call live run; partial failure with no resume path | LOW | MEDIUM | **P2** | `--resume <RUN_ID>` flag wired into TASK-004 T4-2 in-scope and DESIGN-004 §5.1; pre-flight tier check is a T4-5 responsibility. Resolved at plan time. | T4-2 (resume), T4-5 (pre-flight) |
| R7 | ADR number collision with concurrent ADR PRs | MEDIUM | LOW | **P2** | T4-6 reserves the next ADR number at task start; placeholder + full body land in one commit (budget unchanged). Resolved at plan time | T4-6 |
| R8 | T4-7 sized XS underinvests the decision narrative; PR fails architect review | HIGH | MEDIUM | **P1** | T4-7 resized to S; explicit note that decision prose is the work, not the field write. Resolved at plan time | T4-7 |
| R9 | Architect review SLA undefined; PR sits in limbo after T4-6 merges | LOW | LOW | **P2** | TASK-004 T4-7 acceptance criteria now state: if no architect-tier response within 5 business days of PR move-to-ready, set `recommendation` to `keep-as-audit` with `recommendation_default: "sla-fallback"` flag in `report.json`. Resolved at plan time. | T4-7 |
| R10 | `scrap` verdict leaves runner code in `scripts/eval/` (lint, type-check, coverage burden for dead code) | LOW | MEDIUM | **P2** | TASK-004 T4-7 scrap-path archival is now wired into in-scope: runner + 6 modules + test file move to `evals/_archive/security-spike-<RUN_ID>/scripts/`; ADR marked `status: superseded`; T4-7 commit budget bumps to up to 4 commits on scrap path. Resolved at plan time. | T4-7 |
| R11 | T4-5 commits structurally invalid `recommendation: null` | MEDIUM | LOW | **P2** | DESIGN-004 §5.6 schema notes formally declare `recommendation: string \| null`; T4-3 AC explicitly states schema validators MUST accept null on T4-5 records and reject null on T4-7 records. Resolved at plan time. | T4-3, T4-5 |
| R12 | Hidden coupling to ongoing security-scan / ADR-057 work on main | LOW | LOW | **P2** | Spike branch is short-lived; rebase before T4-5 to surface conflicts early. No code overlap expected | implementer |
| R13 | Flakiness contingency exists in PLAN narrative but not wired into spec; runner halts on first variance | MEDIUM | HIGH | **P1** | REQ-004 AC-10 now formalizes the contingency: on `flakiness=true`, re-run flaky fixtures at N=5; mark fixtures with persistent variance as `flaky=true` and exclude from delta with documentation; halt the spike only if >30% of fixtures are flaky. T4-5 acceptance criteria mirror this. Resolved in iteration 4. | T4-3 (definition), T4-5 (execution) |
| R14 | RunRecord serialization shape disagrees between REQ-004 AC-1 (`pattern`/`expected_value`) and DESIGN-004 §5.5 (legacy `value`) | MEDIUM | MEDIUM | **P2** | DESIGN-004 §5.3 `AssertionResult` dataclass now has `pattern` AND `expected_value` (mutually exclusive by `kind`); §5.5 RunRecord example JSON updated to match. REQ-004 AC-1 references `AssertionResult` shape. Resolved in iteration 4. | T4-1 (types), T4-2 (writer) |

### P0 risk summary

Two P0 risks remain at start-of-execution:

1. **R1** (corpus quality) — must be resolved during T4-4 with the pilot gate
2. **R2** (`aggregate_multi_run_scores`) — already mitigated at plan time via TASK-004 + DESIGN-004 fixes

---

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-05-03 | Pick `security` agent for the spike | Crisp deterministic-scorable signal (CWE/STRIDE/OWASP strings); existing scenario JSON to bootstrap from; external grounding signal exists | `qa` (rejected: freeform output, no deterministic scorer); `analyst` (rejected: same); multi-agent first (rejected: methodology unproven) |
| 2026-05-03 | Baseline is deliberately naive (no domain vocabulary) | Iteration-1 BLOCKER: original `"You are a security reviewer..."` baseline pre-specified the agent's task vocabulary and would have produced a false null verdict misread as "agent is decoration" | Original task-vocabulary baseline (rejected); no baseline at all (rejected: no comparison signal) |
| 2026-05-03 | ADR scope bounded to deterministic-scorable agents only | Iteration-1 HIGH: the spike picks the easiest case; the ADR must not over-generalize. Survivorship bias acknowledged. | Generalize to all agents (rejected: methodology fails on freeform output) |
| 2026-05-03 | Decision criteria normative in REQ-004 AC-5 with operational consequences | Iteration-1 BLOCKER: criteria were a task-level note that an architect reading the report could not act on consistently | Criteria only in T4-7 (rejected); criteria in ADR only (rejected: not enforceable on the spike PR) |
| 2026-05-03 | Polymorphic Assertion interface; `pattern` + `expected_value` split (not single `value`) | CVA flagged the assertion layer as the greatest abstraction risk; split prevents a future breaking change when AST and TEST_PASS kinds arrive | Single `value` field with `kind`-dependent semantics (rejected: future breaking change) |
| 2026-05-03 | N=3 runs per (fixture, variant) at temperature=0 | Variance signal at acceptable cost; 60 calls × variants × runs is the budget envelope; standard floor for paired-bootstrap | N=1 (rejected: no variance signal); N=10 (rejected: 200 calls per spike run, cost) |
| 2026-05-03 | Paired-bootstrap n=10000 for the recall-delta CI | Standard non-parametric approach; appropriate for binary-recall metric (no normality assumption); robust to small fixture count | Paired t-test (rejected: assumes normality on a binary outcome); larger bootstrap n (rejected: diminishing returns) |
| 2026-05-03 | "Held-out" means "not used in prior agent eval (notably ADR-057)", NOT "absent from training data" | Iteration-2 critic: original wording conflated two different notions; corpus contamination is a separate concern (deferred to a future ADR) | Define held-out as training-data-clean (rejected: cannot be operationalized for paraphrased CWE inputs) |
| 2026-05-03 | LLM-as-judge advice quality permitted as advisory sidecar only; gated signal stays deterministic | Iteration-1 decision-critic C2: deterministic scoring measures detection recall, not advice quality; the gated signal stays deterministic per the ADR | LLM-as-judge as gated signal (rejected: PRD); no advice-quality measurement at all (rejected: under-measures agent value) |
| 2026-05-03 | Group T4-1..T4-7 into 3 milestones (MS-1: scaffolding+corpus, MS-2: runner+report, MS-3: decision+ADR) | Each milestone is independently shippable and produces user-visible value or de-risks the next. Aligns with the spike's natural decision points. | Single big-bang PR (rejected: too large, no incremental sign-off). 7 PRs (rejected: review fatigue, no logical grouping) |
| 2026-05-03 | T4-4 splits into 3 commits (T4-4a/b/c) | AGENTS.md hard cap ≤5 files per commit; 12 fixture files cannot fit in 2 commits | Bypass rule with audit reason (rejected: rule exists for review-load reasons; not a one-off case) |
| 2026-05-03 | T4-7 resized XS → S | Decision narrative + architect review prep is consistently underestimated | Keep XS, hope it's enough (rejected: critic finding F2) |
| 2026-05-03 | Pricing constants live in `_eval_common.py` (module-public); both `_plan_runner.py` (T4-1) and `_report_aggregator.py` (T4-3) import from one owner | Iteration-3 finding: T4-3 also needs the rates; module-private would force peer-import (smell) or duplication (DRY violation). Single owner is cleanest. | Module-private (rejected: cross-module dep); pass as constructor arg (rejected: noisy); duplicate in both modules (rejected: DRY) |
| 2026-05-03 | `recommendation: null` formally permitted in DESIGN-004 §5.6 schema; T4-3 AC explicitly accepts null on T4-5 records and rejects null on T4-7 records | Iteration-3 finding: schema-validation AC contradicted T4-5's documented `null` output; needs explicit nullable. | Reject null in schema (rejected: forces T4-5+T4-7 merge); merge T4-5+T4-7 (rejected: blurs audit trail) |
| 2026-05-03 | ADR number reserved at start of T4-6 working session; placeholder + body land in one commit | Iteration-3 finding: budget table claimed 1 commit; reservation as a separate commit would have made it 2. Single-session reservation keeps budget honest. | Reserve in T4-1 (rejected: file budget); reserve as separate commit (rejected: budget table inconsistency) |
| 2026-05-03 | Do NOT reuse `aggregate_multi_run_scores`; new module-private helper instead | Existing function averages dimensional LLM-judge scores; binary pass/fail recall has different shape (verified at `_eval_common.py:19-39`) | Adapt the function (rejected: changes its semantics for ADR-057 callers) |
| 2026-05-03 | `evals/README.md` ships in T4-4a, not T4-1 | Iteration-3 finding: adding `_eval_common.py` modify to T4-1 forced the README out of T4-1's 5-file budget; first fixture commit is the natural home | Keep README in T4-1 (rejected: file budget overflow) |
| 2026-05-03 | Flakiness contingency in REQ-004 AC-10: re-run flaky fixtures at N=5; mark fixtures with persistent variance as `flaky=true` and exclude with documentation; halt only if >30% of fixtures flaky | Iteration-3 finding R13: hard halt on any variance left no contingency path; PLAN narrative had a contingency the spec didn't surface | Hard halt on any flakiness (rejected: spike halts on noise); ignore flakiness (rejected: undermines reproducibility claim) |
| 2026-05-03 | T4-7 scrap-path archival in scope; up to 4 commits when scrap | Iteration-3 finding R10: leaving runner code after scrap is dead code (Broken Windows); explicit archive prevents that | Leave runner in place after scrap (rejected: Broken Windows); separate cleanup PR (rejected: orphan PR) |
| 2026-05-03 | Architect SLA = 5 business days from PR move-to-ready; default to `keep-as-audit` with `recommendation_default: "sla-fallback"` flag | Iteration-3 finding R9: process commitment must be in TASK-004 acceptance, not just PLAN narrative | No SLA (rejected: limbo risk); shorter SLA (rejected: tight for Tier 3 review); auto-graduate-to-CI on no-response (rejected: skips review entirely) |
| 2026-05-03 | RunRecord serialization carries `AssertionResult` shape (`kind`, `pattern`, `expected_value`, `passed`, `extracted`) | Iteration-3 finding: REQ-004 AC-1 listed `Assertion` fields; DESIGN §5.5 example used legacy `value`. Aligned both to `AssertionResult` with `pattern` and `expected_value` mirroring the input `Assertion`. | Serialize input `Assertion` only (rejected: loses scorer extraction context); serialize legacy `value` (rejected: ambiguous semantics by `kind`) |

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
