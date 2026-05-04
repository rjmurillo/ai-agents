---
type: task
id: TASK-004
title: Agent Eval Harness Spike
status: todo
priority: P0
complexity: L
related:
  - DESIGN-004
blocked_by: []
blocks: []
assignee: implementer
created: 2026-05-02
updated: 2026-05-02
---

# TASK-004: Agent Eval Harness Spike

## Design Context

- DESIGN-004: Agent Eval Harness Spike: `scripts/eval/eval-agent-vs-baseline.py`, polymorphic `ScoringEngine`, persistence layout, bootstrap CI

## Objective

Build and execute a one-agent eval harness that measures whether the `security` agent prompt outperforms a generic baseline on a held-out fixture corpus. Produce a report with signed recall delta and CI. Write the ADR that encodes the methodology for future agent authors.

---

## AC Traceability Matrix

Every AC in REQ-004 maps to at least one sub-task. ACs that span multiple sub-tasks are listed under each.

| AC | Owning sub-task(s) | Notes |
|---|---|---|
| AC-1 (per-run record) | T4-2 (writes records), T4-3 (consumes records) | `RunRecord` schema lives in T4-1 (`_eval_agent_types.py`); writes happen in T4-2. |
| AC-2 (Markdown + JSON report) | T4-3 | Report generation is fully owned by T4-3. |
| AC-3 (partial-failure accounting) | T4-3 | `recall_with_errors` and `recall_excluding_errors` computed in `ReportAggregator`. |
| AC-4 (corpus integrity) | T4-1 (validator code), T4-4 (corpus content) | Validator implemented in T4-1; corpus produced and validated in T4-4. |
| AC-5 (decision-anchored report) | T4-3 (report fields), T4-7 (recommendation populated) | Report renders the fields in T4-3; the human decision is recorded in T4-7. |
| AC-6 (ADR) | T4-6 | Single owner. |
| AC-7 (schema versioning) | T4-1 (dataclasses + reader guard), T4-2 (writes versioned records) | Reader rejection test added to T4-1 acceptance criteria. |
| AC-8 (dry-run mode) | T4-1 (`PlanRunner`, dry-run path) | Cost estimate fully owned by T4-1; T4-2 only consumes the same plan object on live runs. |
| AC-9 (idempotency) | T4-2 | `RunPersistence.DuplicateRunError`. |
| AC-10 (reproducibility / flakiness) | T4-3 (flakiness detection), T4-5 (live confirmation) | Flakiness flag is computed inside `ReportAggregator`; T4-5 runs the spike and surfaces the result. |

---

## Sub-Tasks

### T4-1: Scaffolding, Fixture Schema, and Assertion Strategy {#t4-1}

**Complexity**: S (2-4 hours)
**Commit tag**: `feat(evals): scaffold eval-agent-vs-baseline runner and fixture schema`
**Files affected** (≤5):

| File | Action | Description |
|---|---|---|
| `scripts/eval/eval-agent-vs-baseline.py` | create | CLI entry point, arg parsing, coordinator |
| `scripts/eval/_eval_agent_types.py` | create | `Fixture`, `Assertion`, `AssertionKind`, `AssertionResult`, `RunRecord`, `Report`, `ExecutionPlan` dataclasses |
| `scripts/eval/_scoring_engine.py` | create | `ScoringEngine`, `RegexScorer`, `VerdictScorer` |
| `scripts/eval/_plan_runner.py` | create | `PlanRunner.build_plan()` + cost estimate. Imports `MODEL_PRICING_RATES_USD_PER_1K_TOKENS` and `PRICING_RATE_AS_OF` from `_eval_common.py`. |
| `scripts/eval/_eval_common.py` | modify | Add module-public constants `MODEL_PRICING_RATES_USD_PER_1K_TOKENS = {"claude-sonnet-4-6": {"input": 0.003, "output": 0.015}}` and `PRICING_RATE_AS_OF = "2026-05-03"`. Both `_plan_runner.py` (T4-1) and `_report_aggregator.py` (T4-3) import from this single owner. No peer-import smell. |

**In Scope**:
- `AssertionKind` enum with `REGEX` and `VERDICT`
- `ScoringEngine.register()` and `score_all()` dispatch
- `FixtureValidator.validate_fixtures()` with all AC-4 checks
- `PlanRunner.build_plan()` with cost estimate (AC-8 dry-run print path)
- `--dry-run` flag wired through CLI: validates fixtures, builds plan, prints planned call count + cost estimate, exits without invoking the model
- `schemaVersion: 1` on all dataclasses

**Out of Scope**: live API calls, persistence, report generation (still T4-2 / T4-3)

**Acceptance Criteria**:
- [ ] `python3 scripts/eval/eval-agent-vs-baseline.py --dry-run --agent security --fixtures evals/security-spike/fixtures/` exits 2 with a clear message (no fixtures yet)
- [ ] After T4-4 lands: same command exits 0 and prints `planned_calls=60`, an estimated token total, and a USD cost estimate computed from the pricing constants populated in this task
- [ ] `PlanRunner` unit tests pass: empty fixtures (raises), 1 fixture × 2 variants × 3 runs = 6 calls, cost-line format matches `^cost_estimate_usd=\d+\.\d+ rate_as_of=\d{4}-\d{2}-\d{2}$`
- [ ] `ScoringEngine` unit tests pass: regex positive, regex negative, verdict match, verdict mismatch, unknown-kind raises
- [ ] `FixtureValidator` unit tests pass: missing field, invalid provenance, valid fixture, schemaVersion=2 raises `SchemaVersionError`
- [ ] All new dataclasses have `schemaVersion: 1` field
- [ ] One test writes a fixture with `schemaVersion: 2` and asserts `SchemaVersionError` is raised (proves the version guard works)
- [ ] No real API call made in any test

**Done when**: `T4-2` can import `_eval_agent_types` and `_scoring_engine` without modification.

---

### T4-2: Runner, Retry, and Idempotency {#t4-2}

**Complexity**: M (4-8 hours)
**Commit tag**: `feat(evals): add runner loop, API adapter, and idempotency guard`
**Files affected** (≤5):

| File | Action | Description |
|---|---|---|
| `scripts/eval/_eval_api_adapter.py` | create | `AnthropicAPIAdapter.call_model()` wrapping `_anthropic_api`; retry + backoff; structured stderr log |
| `scripts/eval/_run_persistence.py` | create | `RunPersistence`: write-temp-then-rename, duplicate key guard, JSONL append |
| `scripts/eval/eval-agent-vs-baseline.py` | modify | Wire `AnthropicAPIAdapter` and `RunPersistence` into run loop; AC-9 duplicate check |
| `tests/evals/test_eval_agent_vs_baseline.py` | create | Unit tests for adapter (mocked) and persistence |

**In Scope**:
- Retry: max 3, exponential backoff (base=1s, max=30s) + jitter; transient categories are 408 / 429 / 5xx / timeout. Any other 4xx (400, 401, 403, 404, 409, etc.) records `outcome=error` immediately with `error_category` set; no retry.
- `temperature=0` enforced
- `(fixture_id, variant, run_index)` idempotency key; `DuplicateRunError` on collision
- `outcome=error` recorded; `error_category` set
- Structured JSON stderr log per call
- Run directory: `evals/security-spike/runs/<RUN_ID>/` (`RUN_ID` = ISO8601 compact + UUID4)
- `prompt_sha` and `fixture_sha` recorded (SHA-256)
- API key from `ANTHROPIC_API_KEY` env; never logged
- `--resume <RUN_ID>` flag: opens an existing run directory, scans `runs.jsonl` for completed `(fixture_id, variant, run_index)` triples, and SKIPS them on this invocation (does NOT raise `DuplicateRunError`). Allows recovery from a partial 60-call live run interrupted by API outage or local interruption. Resume mode and fresh-run mode share the same `RunPersistence` instance; the only difference is whether duplicates are skipped or rejected.

**Out of Scope**: Report generation, bootstrap CI (T4-3); dry-run plan + cost estimate (T4-1)

**Acceptance Criteria**:
- [ ] Adapter unit tests: success path, 429 retry-then-success, 500 retry-then-error, 400 immediate error, timeout retry
- [ ] Persistence tests: first write succeeds, duplicate write raises `DuplicateRunError`, JSONL file parses back to `RunRecord`, `--resume` mode skips already-completed triples (no error) and only invokes the API for missing triples
- [ ] `schemaVersion: 1` on every written record
- [ ] No real API calls in any test (adapter mocked)
- [ ] `ANTHROPIC_API_KEY` not present in any log line (assert in test)
- [ ] Live run path uses the same `ExecutionPlan` produced by `PlanRunner` so per-run accounting matches the dry-run preview (no double-counting, no drift)

**Done when**: Runner can execute one fixture against both variants and produce valid JSONL without errors.

---

### T4-3: Reporting (Recall, Bootstrap CI, Distribution) {#t4-3}

**Complexity**: M (4-8 hours)
**Commit tag**: `feat(evals): add report aggregator and writer with bootstrap CI`
**Files affected** (≤5):

| File | Action | Description |
|---|---|---|
| `scripts/eval/_report_aggregator.py` | create | `ReportAggregator`: recall, `recall_with_errors`, `recall_excluding_errors`, bootstrap CI (n=10000), flakiness flag |
| `scripts/eval/_report_writer.py` | create | `ReportWriter`: render `REPORT.md` + `report.json`; write-temp-then-rename |
| `scripts/eval/eval-agent-vs-baseline.py` | modify | Wire aggregator + writer after run loop |
| `tests/evals/test_eval_agent_vs_baseline.py` | modify | Add aggregator tests: recall formula, CI bounds, flakiness detection |

**In Scope**:
- Recall = `sum(passed_assertions) / sum(total_assertions)` (not fixture count)
- Paired bootstrap (n=10000 resamples at fixture level), 95% CI, signed delta
- Per-fixture pass-rate distribution across N=3 runs
- `recall_with_errors` vs. `recall_excluding_errors` (AC-3)
- Flakiness: pass-rate variance > 0 on same-SHA rerun sets `flakiness=true`
- `recommendation` field in `report.json` (one of: `graduate-to-CI`, `keep-as-audit`, `scrap`)
- Cost estimate: `_report_aggregator.py` imports `MODEL_PRICING_RATES_USD_PER_1K_TOKENS` and `PRICING_RATE_AS_OF` from `_eval_common.py` (constants added in T4-1). Compute `(total_tokens_in × input_rate + total_tokens_out × output_rate) / 1000`. Include `pricing_rate_as_of` in the report so historical reports remain interpretable when rates change.
- **Do NOT reuse** `aggregate_multi_run_scores` from `_eval_common.py`: its signature `(run_scores: list[dict], dimensions: list[str])` averages LLM-judge dimensional scores and does NOT match the binary pass/fail recall used here. Implement a new module-private helper in `_report_aggregator.py`. (Confirmed by reading the function body in `scripts/eval/_eval_common.py:19-39`.)

**Out of Scope**: Actual recommendation logic (human decision in T4-7); this task writes the field but leaves it as `null` until T4-6

**Acceptance Criteria**:
- [ ] `ReportAggregator` unit tests: recall with all pass, recall with all fail, recall with errors, CI bounds non-empty, flakiness=false on identical runs
- [ ] `report.json` validates against schema (all required fields present, `schemaVersion: 1`). The schema accepts `recommendation: null` on records produced by T4-5; T4-7 overwrites with one of three valid strings. Schema validator MUST NOT reject null `recommendation`.
- [ ] `REPORT.md` contains: summary table, per-fixture breakdown, CI section, recommendation section, cost summary
- [ ] Error-rate > 10% causes exit code 1 before report is written
- [ ] Report written with write-temp-then-rename

**Done when**: Running against a fixture set produces both `report.json` and `REPORT.md` with all required fields.

---

### T4-4: Corpus Build (10 Fixtures with Provenance) {#t4-4}

**Complexity**: M (4-8 hours total across three commits)

T4-4 splits into three commits to fit the AGENTS.md ≤5-file rule. The split is mandatory.

#### T4-4a: fixtures part 1 + landscape README {#t4-4a}

**Commit tag**: `feat(evals): seed eval corpus with first fixture batch and landscape README`
**Files affected** (5):

| File | Action | Description |
|---|---|---|
| `evals/README.md` | create | Cross-reference `tests/evals/` (ADR-057); explain purpose of `evals/security-spike/`. Moved from T4-1 to keep T4-1 within budget. |
| `evals/security-spike/fixtures/F001.json` | create | First fixture; `schemaVersion: 1`, `id`, `input`, `provenance`, `assertions[]`, `tags` |
| `evals/security-spike/fixtures/F002.json` | create | Second fixture |
| `evals/security-spike/fixtures/F003.json` | create | Third fixture |
| `evals/security-spike/fixtures/F004.json` | create | Fourth fixture |

**Pilot gate (P0 risk R1 mitigation)**: Before committing, run a single agent-discriminating fixture from this batch through both variants live (one fixture × 2 variants = 2 API calls). Confirm the naive baseline fails it. If the baseline passes the agent-discriminating fixture, redesign the fixture before commit.

#### T4-4b: fixtures part 2 + corpus README {#t4-4b}

**Commit tag**: `feat(evals): add fixture batch 2 and corpus design rationale`
**Files affected** (5):

| File | Action | Description |
|---|---|---|
| `evals/security-spike/fixtures/F005.json` | create | Fifth fixture |
| `evals/security-spike/fixtures/F006.json` | create | Sixth fixture |
| `evals/security-spike/fixtures/F007.json` | create | Seventh fixture |
| `evals/security-spike/fixtures/F008.json` | create | Eighth fixture |
| `evals/security-spike/fixtures/README.md` | create | Corpus provenance notes; per-fixture rationale; explicit "agent-discriminating" section listing which fixtures and why naive baseline cannot score correctly |

#### T4-4c: fixtures part 3 + directory marker {#t4-4c}

**Commit tag**: `feat(evals): finalize corpus to 10 fixtures`
**Files affected** (3):

| File | Action | Description |
|---|---|---|
| `evals/security-spike/fixtures/F009.json` | create | Ninth fixture |
| `evals/security-spike/fixtures/F010.json` | create | Tenth fixture |
| `evals/security-spike/runs/.gitkeep` | create | Reserve runs directory for T4-5 |

**In Scope** (across all three sub-commits):
- 10 fixtures covering `IDENTIFY` (with CWE), `OK`, and `ESCALATE` verdicts
- Provenance: `synthetic` or `paraphrased-from-public`; no real credentials
- Seed from `tests/evals/security-scenarios.json` where re-usable (mark as `paraphrased-from-public`)
- Each fixture has at least one `verdict` assertion; may add `regex` assertions for CWE patterns
- Held-out criterion: fixtures not used in ADR-057 prompt-change eval
- No fixture contains real PII, real tokens, or real third-party secrets
- Pilot gate before T4-4a commits: confirm naive baseline fails the agent-discriminating subset

**Out of Scope**: Corpus expansion to 50+ fixtures (deferred per PRD)

**Acceptance Criteria** (verified after T4-4c):
- [ ] All 10 fixtures pass `FixtureValidator.validate_fixtures()` with zero errors
- [ ] At least 3 fixtures per verdict class (`IDENTIFY`, `OK`, `ESCALATE`)
- [ ] At least 3 **agent-discriminating fixtures** where the correct response requires knowledge only the agent's system prompt encodes (e.g., OWASP/STRIDE framing, project-specific escalation policy, multi-step threat chain reasoning). Documented in `fixtures/README.md` with rationale for why the naive baseline cannot score correctly.
- [ ] Pilot gate executed before T4-4a commit and recorded in PR body (one fixture run live, baseline failed it)
- [ ] Every fixture has `provenance` in `{synthetic, paraphrased-from-public}`
- [ ] `--dry-run` against the complete corpus prints exactly 60 planned API calls (10 fixtures × 2 variants × 3 runs)
- [ ] No fixture fails AC-4 provenance check
- [ ] Each commit ≤5 files (T4-4a: 5, T4-4b: 5, T4-4c: 3)

**Done when**: Dry-run against complete corpus exits 0 and prints 60 planned calls AND all three sub-commits are pushed.

---

### T4-5: Execute Spike and Write Report {#t4-5}

**Complexity**: S (2-4 hours)
**Commit tag**: `feat(evals): execute security agent eval spike and commit report`
**Irreversibility warning**: T4-5 incurs real Anthropic API cost (~$0.09 at current rates per DESIGN-004) and produces a timestamp-keyed run directory. The committed `runs.jsonl` is the audit trail; reverting after T4-6 merges requires a follow-on amendment to the ADR. Validate the corpus and runner end-to-end via `--dry-run` before executing live, and confirm API tier supports 60 sequential calls within session.
**Files affected** (≤5):

| File | Action | Description |
|---|---|---|
| `evals/security-spike/runs/<RUN_ID>/runs.jsonl` | create | 60 run records from live execution |
| `evals/security-spike/reports/<RUN_ID>/report.json` | create | Aggregated report |
| `evals/security-spike/reports/<RUN_ID>/REPORT.md` | create | Human-readable report |

**In Scope**:
- Execute `eval-agent-vs-baseline.py --agent security --fixtures evals/security-spike/fixtures/ --n-runs 3`
- Verify exit code 0
- Verify `flakiness=false` (or document if true and investigate)
- Verify error count = 0 (or document errors)
- Leave `recommendation` as `null`: set in T4-7

**Out of Scope**: Final recommendation (T4-7); ADR (T4-6)

**Acceptance Criteria**:
- [ ] 60 records in `runs.jsonl` (10 fixtures × 2 variants × 3 runs) on first pass; additional records if contingency re-runs were triggered
- [ ] `report.json` present with all required fields
- [ ] If `flakiness=true` on first pass: contingency protocol executed per REQ-004 AC-10: re-run flaky fixtures at N=5; mark `flaky=true` on fixtures with persistent variance; exclude them from delta with a documented note in `REPORT.md`
- [ ] If >30% of fixtures end up `flaky=true`, exit code 1 and stop (methodology unstable; T4-6 cannot proceed)
- [ ] `recall_delta` is a real number with CI bounds (computed on the non-flaky subset if any fixtures were excluded)
- [ ] No API key or response body appears in any committed file other than `runs.jsonl`

**Done when**: Report committed to branch; another engineer can reproduce the run using the committed prompt and fixture SHAs.

---

### T4-6: Write ADR {#t4-6}

**Complexity**: M (4-8 hours)
**Commit tag**: `docs(adr): add ADR-NNN agent eval discipline`
**Files affected** (≤5):

| File | Action | Description |
|---|---|---|
| `.agents/architecture/ADR-NNN-agent-eval-discipline.md` | create | Full ADR covering corpus, scoring, baseline, threshold, cadence |

**In Scope** (all required per AC-6):
- ADR number reservation: at the START of the T4-6 working session, run `ls .agents/architecture/ADR-0*.md | tail -1` to determine the next available number. Claim it locally by creating the file with frontmatter (status: proposed) and the full body in a single working session. The placeholder and full content land in **one commit**, not two: the budget table reflects this. This prevents collision with concurrent ADR PRs while staying within the file budget.
- Corpus structure: fixture schema (all fields + `schemaVersion`), provenance rules, held-out criterion
- Held-out definition: ADR must state explicitly that "held-out" means "not used in prior agent eval (notably ADR-057's prompt-change scenarios)" and NOT "absent from the model's training data"; corpus contamination is acknowledged as out of scope for v1
- Scoring discipline: deterministic-only for gated path; "LLM-as-judge is explicitly rejected as the gated signal" stated verbatim; advice quality acknowledged as a non-gated advisory sidecar option
- Scope boundary: methodology applies only to agents with deterministic-scorable output; freeform-output agents require a different (unspecified) methodology; survivorship bias acknowledged
- Baseline definition: same model + minimal generic prompt that is **deliberately naive** (no domain vocabulary, no role assignment); SHA-locked text from spike
- Threshold methodology: per-agent calibration; no global magic number; bootstrap-CI based; **worked example using the spike's actual numbers** (recall, CI, threshold reasoning)
- CI cost projection: per-run cost × project PR cadence = monthly cost; exact numbers from the spike run
- Decision owner and consequences: architect-tier reviewer ratifies via PR; `graduate-to-CI` opens a follow-up issue, `keep-as-audit` schedules re-run on next model bump, `scrap` archives `evals/security-spike/` and supersedes the ADR
- Re-baseline cadence: model bump or quarterly, whichever first
- Cross-reference ADR-057: distinguish prompt-change before/after vs. agent-vs-baseline efficacy
- Context section: references spike run ID and report

**Out of Scope**: Multi-agent rollout; CI gating (deferred)

**Acceptance Criteria**:
- [ ] ADR follows `.agents/architecture/ADR-*.md` convention (frontmatter, status: proposed)
- [ ] All required sections present: corpus structure, held-out definition, scoring discipline, scope boundary (deterministic-scorable only), baseline (deliberately naive), threshold methodology with worked example, CI cost projection, decision owner + consequences, cadence, ADR-057 cross-reference, advice-quality acknowledgment
- [ ] "LLM-as-judge explicitly rejected" stated in scoring section as the gated signal; advice-quality sidecar position noted as optional advisory
- [ ] "Held-out" definition explicitly distinguishes ADR-057 exclusion from training-data separation
- [ ] Baseline prompt text SHA in ADR matches `agent_prompt_sha`/`baseline_prompt_sha` in `report.json`
- [ ] Worked example references the spike's actual numbers (recall, CI bounds, recommendation rationale)
- [ ] CI cost projection includes per-run × monthly PR cadence multiplier with the date the pricing rate was current
- [ ] Decision owner section names the architect role and the operational consequence of each verdict (graduate / audit / scrap)
- [ ] Survivorship-bias acknowledgment present
- [ ] Cross-reference to ADR-057 present
- [ ] ADR passes `python3 scripts/validation/pre_pr.py` (no BLOCKING issues)

**Done when**: ADR file exists, passes pre-PR validation, and is committed.

---

### T4-7: Decide Graduate-to-CI vs. Audit vs. Scrap {#t4-7}

**Complexity**: S (2-4 hours). The mechanical field write is XS, but the decision narrative: applying the AC-5 criteria, citing two evidence pieces, defending the verdict to architect-tier review: is the actual work and is consistently underestimated.
**Commit tag**: `docs(evals): record spike decision in report`
**Files affected** (≤5):

| File | Action | Description |
|---|---|---|
| `evals/security-spike/reports/<RUN_ID>/report.json` | modify | Set `recommendation` field |
| `evals/security-spike/reports/<RUN_ID>/REPORT.md` | modify | Add decision rationale section |

**In Scope**:
- Read the spike report (T4-5) and the ADR (T4-6)
- Decide: `graduate-to-CI`, `keep-as-audit`, or `scrap`
- Criteria for `graduate-to-CI`: recall delta > 0, CI excludes zero, flakiness=false, error count = 0
- Criteria for `keep-as-audit`: positive delta but CI spans zero OR minor flakiness
- Criteria for `scrap`: no meaningful delta or methodology flaw discovered
- Write decision + at least two pieces of evidence into `REPORT.md` recommendation section
- Update `recommendation` field in `report.json`

**Out of Scope**: Actual CI integration (deferred to architect; trigger: ADR merged + one additional agent eval)

**Scrap-path archival (R10 mitigation)**: If the recommendation is `scrap`, T4-7 also moves the runner code and tests to the archive:
- Move `scripts/eval/eval-agent-vs-baseline.py` and the six new modules (`_eval_agent_types.py`, `_scoring_engine.py`, `_plan_runner.py`, `_eval_api_adapter.py`, `_run_persistence.py`, `_report_aggregator.py`, `_report_writer.py`) to `evals/_archive/security-spike-<RUN_ID>/scripts/`
- Move `tests/evals/test_eval_agent_vs_baseline.py` to the same archive directory
- Update the ADR frontmatter to `status: superseded` with a successor-ADR reference
- Restore the `MODEL_PRICING_RATES_USD_PER_1K_TOKENS` and `PRICING_RATE_AS_OF` constants in `_eval_common.py` only if no other module still uses them (greedy-cleanup)

The archival commit is a **fourth commit** in this task (T4-7 totals 4 commits when scrap; 1 commit when graduate-to-CI or keep-as-audit). Each archival commit ≤5 files.

**Acceptance Criteria**:
- [ ] `recommendation` field set to one of the three valid strings (overwrites the `null` left by T4-5)
- [ ] At least two evidence bullets in `REPORT.md` recommendation section
- [ ] If `graduate-to-CI`: delta > 0, CI lower bound > 0, stated explicitly
- [ ] If `keep-as-audit` or `scrap`: reason documented with reference to specific metric
- [ ] If `scrap`: scrap-path archival executed; ADR `status: superseded`; runner+tests moved to `evals/_archive/security-spike-<RUN_ID>/scripts/`
- [ ] Decision defensible to architect review (Tier 3 rigor)
- [ ] **SLA fallback (R9 mitigation)**: if no architect-tier review response within 5 business days of the spike PR being moved out of draft, the implementer sets `recommendation` to `keep-as-audit` with a `REPORT.md` note `"pending review"` and the SLA-default flag `recommendation_default: "sla-fallback"` in `report.json`. Default does NOT graduate to CI without review and does NOT scrap prematurely.

**Done when**: `recommendation` field populated, report committed, PR ready for architect review.

---

## Sequencing and Dependencies

```
T4-1 (scaffolding)
  → T4-2 (runner + persistence)
    → T4-3 (reporting)
      → T4-4 (corpus)   [can start in parallel with T4-3]
        → T4-5 (execute)
          → T4-6 (ADR)
            → T4-7 (decision)
```

T4-4 may be started as soon as T4-1 is complete (fixture schema is defined). T4-3 and T4-4 may proceed in parallel.

---

## Commit Budget (AGENTS.md: ≤5 files, ≤20 commits/PR)

| Sub-task | Commits | Files |
|---|---|---|
| T4-1 | 1 | 5 |
| T4-2 | 1 | 4 |
| T4-3 | 1 | 4 |
| T4-4a | 1 | 5 (F001-F004 + evals/README.md) |
| T4-4b | 1 | 5 (F005-F008 + fixtures/README.md) |
| T4-4c | 1 | 3 (F009-F010 + runs/.gitkeep) |
| T4-5 | 1 | 3 |
| T4-6 | 1 | 1 |
| T4-7 | 1-4 | 2 (graduate-to-CI or keep-as-audit) OR up to 9 files across 4 commits (scrap path: archives runner + 6 modules + test file) |
| **Total** | **9 (typical): up to 12 (scrap path)** | **~31 hours typical; +1-3 hours for scrap-path archival** |

T4-4 MUST split into three commits (T4-4a/b/c). Each commit ≤5 files per AGENTS.md. The split is mandatory. T4-7's commit count varies with the verdict: see scrap-path archival in T4-7 in-scope.

---

## Testing Requirements

- All tests under `tests/evals/test_eval_agent_vs_baseline.py`
- `pytest 8+`
- Mock API at `AnthropicAPIAdapter` boundary; no live API calls in tests
- Coverage targets per AGENTS.md: 100% security-critical paths (key handling, provenance rejection), 80% business logic (scoring, recall, CI), 60% glue (CLI wiring, report rendering)

---

## Files Affected (Summary)

| File | Task | Action |
|---|---|---|
| `scripts/eval/eval-agent-vs-baseline.py` | T4-1, T4-2, T4-3 | create, extend |
| `scripts/eval/_eval_agent_types.py` | T4-1 | create |
| `scripts/eval/_scoring_engine.py` | T4-1 | create |
| `scripts/eval/_eval_api_adapter.py` | T4-2 | create |
| `scripts/eval/_run_persistence.py` | T4-2 | create |
| `scripts/eval/_report_aggregator.py` | T4-3 | create |
| `scripts/eval/_report_writer.py` | T4-3 | create |
| `tests/evals/test_eval_agent_vs_baseline.py` | T4-2, T4-3 | create, extend |
| `evals/README.md` | T4-4a | create |
| `evals/security-spike/fixtures/F001-F010.json` | T4-4 | create |
| `evals/security-spike/fixtures/README.md` | T4-4 | create |
| `evals/security-spike/runs/<RUN_ID>/runs.jsonl` | T4-5 | create |
| `evals/security-spike/reports/<RUN_ID>/report.json` | T4-5, T4-7 | create, modify |
| `evals/security-spike/reports/<RUN_ID>/REPORT.md` | T4-5, T4-7 | create, modify |
| `.agents/architecture/ADR-NNN-agent-eval-discipline.md` | T4-6 | create |

---

## Related Documents

- Requirements: `.agents/specs/requirements/REQ-004-agent-eval-harness-spike.md`
- Design: `.agents/specs/design/DESIGN-004-agent-eval-harness-spike.md`
- Issue: rjmurillo/ai-agents#1854
- ADR-057: `.agents/architecture/ADR-057-prompt-behavioral-evaluation.md`
