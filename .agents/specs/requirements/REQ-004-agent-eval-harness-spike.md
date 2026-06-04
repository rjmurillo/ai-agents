---
type: requirement
id: REQ-004
title: Agent Eval Harness Spike
status: draft
priority: P0
category: non-functional
epic: SPIKE-1854
related:
  - DESIGN-004
author: spec-agent
created: 2026-05-02
updated: 2026-05-04
---

# REQ-004: Agent Eval Harness Spike

## Context

The project has no mechanism that proves a given agent's context recipe produces measurably better outputs than the same model with a generic prompt. This spike learns what shape an "agent works" eval takes for ONE agent (the `security` agent), then writes the ADR that describes how to scale the methodology, or whether to.

Three user stories frame the need:

- **US-1**: An agent maintainer runs a deterministic eval comparing the agent prompt vs. the same model with a generic prompt on a held-out corpus and gets a numeric delta plus a pass/fail signal that survives reruns.
- **US-2**: An architect reads the merged ADR at `.agents/architecture/ADR-NNN-agent-eval-discipline.md` and decides among {graduate-to-CI, keep-as-audit, scrap}.
- **US-3**: A future agent author applies the ADR methodology (corpus, scoring, baseline, threshold, cadence) without re-deriving it.

---

## Requirement Clusters

### Cluster A: Spike Runner: Record, Reproduce, Report {#req-cluster-a}

Covers AC-1, AC-2, AC-3, AC-7, AC-8, AC-9, AC-10.

#### AC-1: Per-run record {#req-ac1}

**Requirement Statement**

WHEN the spike runner is invoked with the security agent's prompt and the held-out fixture set,
THE SYSTEM SHALL produce a JSONL record per (fixture, variant, run_index) containing model_id, variant, prompt_sha, fixture_sha, raw response, parsed assertions with pass/fail per assertion, and timing/token metadata,
SO THAT every result is reproducible and reviewable.

**Acceptance Criteria**

- [ ] Each record written to `evals/security-spike/runs/<RUN_ID>/runs.jsonl`
- [ ] Record contains: `fixture_id`, `variant` (agent|baseline), `run_index`, `model_id`, `prompt_sha`, `prompt_ref` (path to source, agent template path or literal `<baseline>`), `fixture_sha`, `raw_response`, `assertions[]` (each row carries the serialized `AssertionResult`: `kind`, `pattern` or `expected_value` (whichever is set on the input `Assertion`), `passed`, `extracted`), `latency_ms`, `tokens_in`, `tokens_out`, `outcome`, `error_category`, `attempts`
- [ ] `schemaVersion: 1` present on every record
- [ ] Two variants always recorded: `agent` and `baseline`
- [ ] Three run indices (0, 1, 2) produced per (fixture, variant) tuple

**Dependencies**: Fixture schema (AC-4); baseline prompt definition (OQ-5)

---

#### AC-2: Markdown + JSON report {#req-ac2}

**Requirement Statement**

WHEN the runner finishes,
THE SYSTEM SHALL emit a Markdown report at `evals/security-spike/reports/<RUN_ID>/REPORT.md` containing per-variant recall, per-fixture pass-rate distribution across N=3 runs, paired-bootstrap CI on the recall delta, and a sidecar `report.json` with the same data,
SO THAT the spike's findings are inspectable and re-derivable.

**Acceptance Criteria**

- [ ] `REPORT.md` created at `evals/security-spike/reports/<RUN_ID>/REPORT.md`
- [ ] `report.json` sidecar created in same directory with same data
- [ ] Report includes per-variant recall (agent recall, baseline recall)
- [ ] Report includes per-fixture pass-rate distribution across N=3 runs
- [ ] Report includes paired-bootstrap CI (95%) on the recall delta (signed)
- [ ] Report includes total tokens, wall-clock time, and cost estimate
- [ ] Report includes `flakiness` boolean: `true` if any fixture has non-zero pass-rate variance across N runs on the same `(prompt_sha, fixture_set_sha)`; `false` otherwise. Same definition as AC-10.
- [ ] `report.json` contains `schemaVersion: 1`

**Dependencies**: AC-1 complete; AC-3 error accounting

---

#### AC-3: Partial-failure accounting {#req-ac3}

**Requirement Statement**

WHEN any fixture fails irrecoverably (>= max retries on transient error),
THE SYSTEM SHALL record the run with `outcome=error` and emit `recall_with_errors` and `recall_excluding_errors` separately in the report,
SO THAT a transient outage does not silently change the headline number.

**Acceptance Criteria**

- [ ] Fixture with `outcome=error` counted separately in report
- [ ] `recall_with_errors` and `recall_excluding_errors` both present in `report.json`
- [ ] Run with error rate > 10% fails the spike with typed exit code `1` and a structured error message
- [ ] Error records contain `error_category` field

**Dependencies**: Retry policy (DESIGN-004 §Failure Modes)

---

#### AC-7: Schema versioning {#req-ac7}

**Requirement Statement**

WHEN the runner persists state,
THE SYSTEM SHALL include `schemaVersion` on every JSON record and reject reads against unknown major versions,
SO THAT future schema evolution does not silently corrupt historical data.

**Acceptance Criteria**

- [ ] `schemaVersion: 1` on every fixture, run record, and report JSON
- [ ] Reader raises a typed error if `schemaVersion` is absent or major version > 1
- [ ] Schema version bump documented as a two-step migration (stop writing old field → deprecate → remove)

**Dependencies**: None

---

#### AC-8: Dry-run mode {#req-ac8}

**Requirement Statement**

WHEN the runner is invoked with `--dry-run`,
THE SYSTEM SHALL load fixtures, validate them, print the planned API call count and estimated cost, and exit without invoking the model,
SO THAT cost surprises are avoided before commit.

**Acceptance Criteria**

- [ ] `--dry-run` flag accepted; no API calls made
- [ ] Fixture count, variant count, run-index count, and total planned call count printed to stdout
- [ ] Cost estimate printed (tokens × rate)
- [ ] Exit code 0 on valid fixtures; exit code 2 on fixture validation failure

**Dependencies**: AC-4 fixture validation

---

#### AC-9: Idempotency guard {#req-ac9}

**Requirement Statement**

WHEN the same `(fixture_id, variant, run_index)` triple appears more than once in a run directory,
THE SYSTEM SHALL fail with a duplicate-write error,
SO THAT idempotency violations are detected loudly.

**Acceptance Criteria**

- [ ] Runner checks existing JSONL records before writing each new record
- [ ] Duplicate triple raises a typed `DuplicateRunError` with the conflicting key
- [ ] Process exits with code 1 on duplicate detection
- [ ] Error message includes run directory path and the duplicate key

**Dependencies**: Filesystem persistence (DESIGN-004 §Persistence Layout)

---

#### AC-10: Reproducibility / flakiness gate {#req-ac10}

**Requirement Statement**

WHEN the eval is run on the same prompt-variant SHA against the same fixture-set SHA twice,
THE SYSTEM SHALL produce statistically indistinguishable recall (within bootstrap CI), or fail the spike with a flakiness flag,
SO THAT the methodology produces a usable signal at all.

**Acceptance Criteria**

- [ ] `prompt_sha` and fixture-set SHA recorded in `report.json`
- [ ] Flakiness is defined as: any fixture with non-zero pass-rate variance across N runs on the same (prompt_sha, fixture_set_sha). If any fixture has variance > 0, `flakiness=true` is set in `report.json`.
- [ ] On detection of `flakiness=true`, the operator SHALL re-run the spike at N=5 (a contingency-mode rerun, not a halt). The aggregator marks any fixture whose pass rate variance persists for ≥2 of 5 reps on the same fixture as `flaky=true` in its `flaky_fixtures_detected` array and EXCLUDES it from the recall delta calculation, with the exclusion documented in `REPORT.md` as a finding. _Note (2026-05-03): the spec originally asked for the runner to perform the contingency rerun automatically in-process. The shipped harness exposes the contingency through `--n-runs 5` and the aggregator's `CONTINGENCY_PERSISTENT_THRESHOLD` constant, leaving the rerun trigger to the operator. Automatic in-process contingency rerun is tracked as a follow-on enhancement._
- [ ] If after the contingency re-run, more than 30% of fixtures are marked `flaky=true`, the spike halts with exit code 1 and a structured message; the methodology itself is unstable and the spike does not produce a `graduate-to-CI` / `keep-as-audit` / `scrap` verdict. The runner SHALL still write `report.json` and `REPORT.md` for the halt path with `recommendation="halt-due-to-flakiness"` so the audit trail is reproducible from the runner.
- [ ] If 30% or fewer fixtures are marked `flaky=true`, the spike continues and the report includes both the recall on the stable subset AND the count of excluded flaky fixtures.
- [ ] Temperature=0 enforced on all API calls

**Dependencies**: AC-2 report; AC-1 SHA recording

---

### Cluster B: Fixture Validation {#req-cluster-b}

Covers AC-4.

#### AC-4: Corpus integrity {#req-ac4}

**Requirement Statement**

WHEN the held-out fixture set is loaded,
THE SYSTEM SHALL fail closed if a fixture is missing required fields (`id`, `input`, `provenance`, `assertions[]`) or if `provenance` indicates real third-party secrets,
SO THAT the corpus stays clean.

**Acceptance Criteria**

- [ ] Validation checks: `id`, `input`, `provenance`, `assertions[]` all present and non-empty
- [ ] `provenance` must be one of: `synthetic`, `public-cve`, `paraphrased-from-public`
- [ ] `schemaVersion` must equal `1`; any other value (including missing) raises `SchemaVersionError` and exits 2
- [ ] `tags` (if present) must be a `list[str]` and each tag matches `^[a-z0-9][a-z0-9_:-]{0,63}$`; invalid tags exit 2
- [ ] Any fixture with `provenance` indicating real credentials, tokens, or third-party secrets is rejected at ingest with exit code 2
- [ ] Validation error message names the offending fixture id and field
- [ ] Validation runs before any API call (enforced by `--dry-run` flow too)
- [ ] Empty fixtures directory (zero `.json` files) exits with code 2 and message `no fixtures found at <path>`, matches the "config" exit class per AGENTS.md

**Dependencies**: Fixture schema (DESIGN-004 §Data Model)

---

### Cluster C: Spike Report and Decision {#req-cluster-c}

Covers AC-5.

#### AC-5: Decision-anchored report {#req-ac5}

**Requirement Statement**

WHEN the spike report is committed,
THE SYSTEM SHALL include the actual deltas (signed, with CI), an honest interpretation of whether the agent demonstrably outperforms baseline on this corpus, a minimum detectable effect size given the fixture count, a differential diagnosis if delta is near zero, and a recommendation among {graduate-to-CI, keep-as-audit, scrap} selected by the decision criteria below with the evidence supporting it,
SO THAT the decision is anchored in measured behavior, not opinion.

**Decision Criteria (normative)**

| Recommendation value | Decision branch | Criteria | Operational consequence |
|---|---|---|---|
| `graduate-to-CI` | evidence-backed positive delta | recall delta > 0 AND 95% CI lower bound > 0 AND flakiness = false AND error count = 0 | A follow-up issue is opened in the project tracker for CI integration scoped to the security agent only; multi-agent rollout remains deferred. |
| `keep-as-audit` | inconclusive positive signal | positive delta but CI spans zero, OR minor flakiness, OR error count > 0 but < 10% | Runner remains offline-only. A re-run is scheduled for the next Anthropic model bump or quarterly, whichever first. The ADR cadence section is the authoritative trigger. |
| `scrap` | methodology flaw | a methodology flaw is discovered during the spike (the experiment design itself was wrong) | The runner (`scripts/eval/eval-agent-vs-baseline.py` plus its six modules and tests) AND the corpus and run directory are moved to `evals/_archive/security-spike-<RUN_ID>/`; the ADR is marked `status: superseded` with a successor ADR documenting the methodology flaw and what would be tried instead. The decision is not face-saving, `scrap` is a real outcome and the spec treats it as such. |
| `scrap` | negative or null delta, or fixed bug | no meaningful delta (CI centered on zero or negative) on a sound methodology, OR an implementation bug that has since been fixed | Only the corpus and run directory are moved to `evals/_archive/security-spike-<RUN_ID>/`. The runner stays in `scripts/eval/` because the methodology is sound and lives on for the next agent. The ADR stays at its prior status (it is NOT superseded). The agent under test loses its eval; the methodology-as-code is preserved. |

**Decision owner**: the architect role, via Tier 3 architecture review. The decision MUST be ratified in PR review by an architect-tier reviewer before the report is merged.

**ADR follow-up**: ADR-058's normative scrap table should mirror this two-cause split. That edit is deferred to a dedicated adr-review pass (an ADR edit fires the BLOCKING adr-review consensus gate, which is out of scope for this spec change). See issue #1876.

**Differential diagnosis for delta near zero**

When the 95% CI includes zero, the report MUST include a differential diagnosis among these four causes:

1. Agent adds no value over the baseline for this task.
2. Baseline is too specific (contains the task vocabulary the agent specializes in).
3. Corpus is too easy (both variants score near 100%).
4. Corpus is too hard (both variants score near 0%).

Each cause must be addressed with evidence from the run data (e.g., per-fixture pass rates, baseline prompt analysis).

**Statistical power acknowledgment**

The report MUST state the minimum detectable effect size given the fixture count (e.g., with N=10 paired observations, the experiment can reliably detect only large effects > ~0.30). The report MUST NOT claim "no difference" when the experiment lacks statistical power to detect small differences. If the result is inconclusive, the recommended next step is "expand corpus."

**Acceptance Criteria**

- [ ] Report states agent recall, baseline recall, signed delta, and 95% bootstrap CI bounds
- [ ] Report MAY include an "Advice Quality (Advisory)" section using LLM-as-judge scoring on the agent's narrative response (mitigation specificity, STRIDE classification correctness, etc.). This section is **non-gated**, it informs the human reviewer but never determines the recommendation verdict. Section MUST be labeled `Advisory: not part of the gated signal.` if included. Deterministic recall remains the only metric that drives the decision criteria.
- [ ] Report states whether the delta is statistically significant (CI excludes zero)
- [ ] Report states the minimum detectable effect size given fixture count
- [ ] Report includes differential diagnosis when 95% CI includes zero (all four causes addressed)
- [ ] Report includes one of four recommendation verdicts: `graduate-to-CI`, `keep-as-audit`, `scrap`, or `halt-due-to-flakiness` (the halt verdict is reserved for AC-10's flakiness gate)
- [ ] Recommendation matches the decision criteria table above
- [ ] Recommendation is supported by at least two pieces of cited evidence from the run data
- [ ] `report.json` contains `recommendation` field. The field MAY be `null` on records produced by T4-5 (decision pending); T4-7 MUST overwrite with one of `"graduate-to-CI" | "keep-as-audit" | "scrap" | "halt-due-to-flakiness"`. The halt verdict is set automatically by the runner when AC-10's flakiness gate trips and supersedes T4-7's manual decision. Schema validators MUST accept null on T4-5 records and reject null on T4-7 records.

**Dependencies**: AC-2 report; bootstrap CI implementation (DESIGN-004 §Scoring)

---

### Cluster D: ADR Methodology Documentation {#req-cluster-d}

Covers AC-6.

#### AC-6: ADR: eval discipline {#req-ac6}

**Requirement Statement**

WHEN the ADR is merged,
THE SYSTEM SHALL document at `.agents/architecture/ADR-NNN-agent-eval-discipline.md`: (a) corpus structure (fixture schema, provenance rules, held-out criterion), (b) scoring discipline (deterministic-only for the gated path; LLM-as-judge explicitly rejected for agent-vs-baseline), (c) baseline definition (same model + minimal generic prompt, version-pinned), (d) threshold-setting methodology (per-agent calibration, no global magic number), (e) re-baseline cadence (after model bump or quarterly, whichever first),
SO THAT future agent authors apply the same discipline without re-deriving it.

**Acceptance Criteria**

- [ ] ADR file exists at `.agents/architecture/ADR-NNN-agent-eval-discipline.md`
- [ ] Fixture schema section covers all required fields plus `schemaVersion`
- [ ] Provenance rules explicitly reject real credentials and third-party secrets
- [ ] Scoring section states "LLM-as-judge is explicitly rejected as the gated signal"
- [ ] Baseline section includes the SHA-locked generic prompt text used in the spike
- [ ] Threshold section states "no global magic number; per-agent calibration required"
- [ ] Cadence section defines re-baseline trigger: model bump or quarterly, whichever first
- [ ] ADR cross-references ADR-057 and states the distinction (prompt-change before/after vs. agent-vs-baseline efficacy)
- [ ] ADR scope section states: "This methodology applies to agents with deterministic-scorable output (structured verdicts, pattern-matchable identifiers). Agents with freeform output require a different methodology not covered by this ADR."
- [ ] ADR "Held-out" definition section states verbatim: "'Held-out' in this ADR means the fixtures were not used in any prior agent eval (notably ADR-057's prompt-change scenarios). It does NOT mean the fixtures are absent from the model's training data. Public CWE descriptions paraphrased into fixtures may have been seen by the model in training. This spike tests prompt specialization on familiar territory, not generalization to novel inputs. Corpus purity beyond provenance tagging is out of scope for v1; a future ADR may add a contamination-detection step."
- [ ] ADR includes "Baseline selection" subsection: baseline must NOT contain the task-specific vocabulary the agent specializes in; it must be deliberately naive
- [ ] ADR includes a worked example of threshold calibration using the spike's actual numbers
- [ ] ADR includes "CI cost projection" section: estimated cost per run at the project's PR cadence (e.g., (planned_calls × tokens × rate) × monthly PR count = monthly cost)
- [ ] ADR includes "Decision owner and scrap consequences" subsection: names the role (architect, via Tier 3 architecture review) that owns the graduate/audit/scrap decision; defines what each decision means operationally, `graduate-to-CI` triggers CI integration follow-up issue; `keep-as-audit` leaves the runner as offline-only and schedules a re-run on next model bump; `scrap` has two operational branches: methodology flaw archives the runner, corpus, and run directory and marks the ADR `status: superseded` with a successor ADR explaining the flaw, while negative or null delta on a sound methodology, or a fixed implementation bug, archives only the corpus and run directory and preserves the runner and ADR status.
- [ ] ADR acknowledges survivorship bias: security was chosen because it has the crispest deterministic signal; not all agents are like security
- [ ] ADR addresses the "advice quality" gap explicitly: deterministic scoring measures detection recall, not advice quality. The spike report MAY include an LLM-as-judge sidecar for advice quality as advisory data only; the gated signal is deterministic recall.

**Dependencies**: Spike report committed (AC-5)

---

## Rationale

The project ships specialized agent prompts but has no empirical evidence that specialization helps. Without a reproducible eval methodology, every agent is a bet without data. This spike de-risks the methodology before scaling it. The ADR makes the methodology a first-class artifact rather than tribal knowledge.

## Dependencies

- `scripts/eval/_anthropic_api.py`, reuse `load_api_key()` and retry logic
- `scripts/eval/_eval_common.py`, reuse `EST_TOKENS_PER_CALL` only; `aggregate_multi_run_scores` is for LLM-as-judge dimensional averaging and is **not** reused (binary pass/fail recall has a different shape)
- `tests/evals/security-scenarios.json`, bootstrap material for fixture corpus
- ADR-057, cross-reference; do not conflict
- `.claude/rules/security.md` and `.agents/governance/SECURITY-REVIEW-PROTOCOL.md`, security constraints

## Out of Scope

- Multi-agent coverage
- Hard-coded delta thresholds
- CI gating (deferred until ADR merged and methodology validated)
- LLM-as-judge as gated signal
- Cost-budget enforcement at runtime
- Re-running ADR-057 prompt-change validation

## Related Documents

- Design: `.agents/specs/design/DESIGN-004-agent-eval-harness-spike.md`
- Tasks: `.agents/specs/tasks/TASK-004-agent-eval-harness-spike.md`
- Issue: rjmurillo/ai-agents#1854
- ADR-057: `.agents/architecture/ADR-057-prompt-behavioral-evaluation.md`
