---
status: proposed
date: 2026-05-03
decision-makers: ["architect", "user"]
consulted: ["qa", "security", "critic", "analyst", "implementer"]
informed: ["devops", "memory"]
---

# ADR-058: Agent Eval Discipline (Agent-vs-Baseline Efficacy)

## Context and Problem Statement

The project ships specialized agent prompts (security, qa, architect, analyst, and others) and asks readers to trust that each prompt produces measurably better outputs than the same model with a generic prompt. There is no empirical evidence to justify that trust. Each agent is a bet without data.

ADR-057 closed one half of this gap. It defined a methodology to detect behavioral *regressions* introduced by editing an existing prompt (before/after on the same artifact). It did not address the prior question: does the agent specialization beat a deliberately naive baseline at all?

Issue #1854 framed the prior question and authorized a spike to learn what shape an agent-vs-baseline eval takes for one agent (`security`), then to write the ADR that codifies the methodology for future agent authors. The spike completed on 2026-05-03 (run `20260503T165136Z-84f918a9`). This ADR records the methodology validated by that spike.

This ADR is offline-only. It is not a CI gate. CI graduation, if it happens, is a follow-up decision driven by per-agent calibration data, not by this ADR.

## Decision Drivers

1. **Empirical validation**: agent specialization claims need data, not intuition.
2. **Reproducibility**: an eval that produces a different signal each time it runs is not a signal.
3. **Scope honesty**: the methodology must work on deterministic-scorable agents and must not over-promise on freeform agents.
4. **Survivorship bias awareness**: the security agent was chosen for the spike because it has the crispest deterministic signal. Not all agents are like security.
5. **Cost discipline**: methodology must produce its signal for a defensible API cost per run.
6. **Distinction from ADR-057**: this ADR is between-subjects (agent vs. baseline). ADR-057 is before-after (prompt edit regression). They are complementary, not overlapping.

## Distinction from ADR-057

| Question | ADR | Comparison |
|---|---|---|
| "Did this prompt edit regress behavior?" | ADR-057 | Same prompt at two SHAs (before vs. after the edit). |
| "Does the agent specialization beat a generic prompt?" | ADR-058 (this ADR) | Agent prompt vs. deliberately-naive baseline at one SHA. |

A prompt change that affects the agent body should be evaluated against both gates: ADR-057 catches regression on existing scenarios; ADR-058 confirms the change still beats a generic baseline.

## Decision

Adopt the agent-vs-baseline efficacy methodology defined below as the standard for empirical validation of agent specialization. The methodology is offline-only at v1. It produces a deterministic-only gated signal, supplemented by an optional advisory LLM-as-judge sidecar.

### Scope

This methodology applies to agents with **deterministic-scorable output**: agents whose responses contain structured verdicts, pattern-matchable identifiers (CWE numbers, STRIDE categories, severity labels), or other content that can be checked against assertions without LLM judgment. Agents with freeform output (open-ended advice, narrative summaries, multi-step plans) require a different methodology not covered by this ADR.

### Survivorship Bias Acknowledgment

The security agent was chosen as the v1 spike subject because its outputs include CWE identifiers and STRIDE categories that can be matched against fixture assertions. This made the methodology easy to demonstrate. It also means this ADR's evidence base is the agent most amenable to deterministic scoring. Generalization to other agents (analyst, qa, architect) requires per-agent calibration and may surface that the methodology does not transfer cleanly. The ADR does not claim that every agent has a deterministic signal of this quality.

### Held-Out Definition

"Held-out" in this ADR means the fixtures were not used in any prior agent eval (notably ADR-057's prompt-change scenarios). It does NOT mean the fixtures are absent from the model's training data. Public CWE descriptions paraphrased into fixtures may have been seen by the model in training. This spike tests prompt specialization on familiar territory, not generalization to novel inputs. Corpus purity beyond provenance tagging is out of scope for v1; a future ADR may add a contamination-detection step.

### Fixture Schema

Fixtures are JSON files with the following required fields:

| Field | Type | Constraint |
|---|---|---|
| `schemaVersion` | int | Must equal `1`. Other values raise `SchemaVersionError` and exit 2. |
| `id` | string | Unique per fixture. Used as natural key for idempotency. |
| `input` | string | The scenario the agent is asked to analyze. |
| `provenance` | string | One of `synthetic`, `public-cve`, `paraphrased-from-public`. |
| `assertions` | list | Non-empty list of assertion records. Each assertion has `kind` (`regex` or `verdict`), plus `pattern` or `expected_value`. |
| `tags` | list[str] | Optional. Each tag matches `^[a-z0-9][a-z0-9_:-]{0,63}$`. Advisory metadata; does not gate. |

**Provenance rules**:

- `synthetic`: written from scratch for this corpus.
- `public-cve`: derived from a public CWE description in the MITRE corpus.
- `paraphrased-from-public`: rewritten from a public source to avoid verbatim training overlap.

Real third-party secrets, customer code, and credentials are rejected at ingest. The validator exits with code 2 and names the offending fixture id and field.

### Scoring Discipline

**Deterministic-only for the gated signal.** The gate's pass/fail decision uses recall against assertions of kind `regex` or `verdict`. LLM-as-judge is explicitly rejected as the gated signal because it confounds two probabilistic systems and makes drift in the judge prompt indistinguishable from drift in the agent under test.

The runner MAY emit an advisory LLM-as-judge sidecar that scores narrative quality (mitigation specificity, STRIDE classification correctness, advice clarity). When present, this sidecar MUST be labeled `Advisory: not part of the gated signal.` and MUST NOT influence the recommendation verdict.

### Baseline Definition

The baseline is the **same model** as the agent under test, invoked with a **deliberately naive generic prompt** that does NOT contain the task-specific vocabulary the agent specializes in. The baseline must be:

1. **Pinned**: the baseline prompt text is version-controlled in the runner repo and recorded by SHA in every run record.
2. **Deliberately naive**: written without security or domain vocabulary. A baseline that contains the agent's specialized terms trivially closes the recall gap and makes the comparison meaningless.
3. **Reviewed on edit**: any change to the baseline file invalidates prior deltas. The PR that edits the baseline must declare the prior corpus' deltas comparative-only, not historical-trend material.

The v1 spike's baseline is a one-paragraph generic-LLM prompt asking the model to identify any issues in the input. The exact text is preserved in the runner code at `scripts/eval/eval-agent-vs-baseline.py` and recorded in every run record under `prompt_ref=<baseline>` with `prompt_sha`.

### Threshold-Setting Methodology

**No global magic number. Per-agent calibration required.** A single recall delta threshold (for example "agent must beat baseline by 10 percentage points") would over-fit to whichever agent set it and would produce false confidence on the next agent measured.

For each agent, the threshold is set by:

1. Run the agent-vs-baseline eval at N=3 with the agent's held-out fixtures.
2. Compute the signed recall delta and the 95% paired-bootstrap CI at the fixture level.
3. Apply the decision criteria below.

There is no single threshold. The threshold is the CI lower bound > 0 in conjunction with flakiness=false and error count = 0.

### Decision Criteria (Normative)

| Recommendation | Criteria | Operational Consequence |
|---|---|---|
| `graduate-to-CI` | recall delta > 0 AND 95% CI lower bound > 0 AND flakiness = false AND error count = 0 | A follow-up issue is opened in the project tracker for CI integration scoped to the agent under test only. Multi-agent rollout remains deferred. CI integration requires a separate security review of the runner's API surface. |
| `keep-as-audit` | positive delta but CI spans zero, OR minor flakiness, OR error count > 0 but < 10% | Runner remains offline-only. A re-run is scheduled for the next Anthropic model bump or quarterly, whichever first. |
| `scrap` | no meaningful delta (CI centered on zero or negative), OR methodology flaw discovered during spike | `evals/<agent>-spike/` is moved to `evals/_archive/<agent>-spike-<RUN_ID>/`. The methodology ADR (this one or its successor) is marked `status: superseded` with a successor ADR documenting the methodology flaw and what would be tried instead. |

These criteria are normative. The ADR does not soften "scrap" into "needs more work." `scrap` is a real outcome and the methodology treats it as such.

### Decision Owner and SLA

The architect role owns the graduate/audit/scrap decision via Tier 3 architecture review. The decision MUST be ratified in PR review by an architect-tier reviewer before the verdict is committed.

**SLA fallback**: if no architect-tier reviewer ratifies the verdict within 5 business days of the spike report's PR opening, the decision defaults to `keep-as-audit`. The runner remains offline-only and the next-quarter review serves as the next decision point. This prevents indefinite limbo without forcing a premature `graduate-to-CI` or `scrap`.

### Re-Baseline Cadence

The eval is re-run on the following triggers, whichever comes first:

1. **Anthropic model version bump** (e.g., sonnet-4-6 to sonnet-4-7 or to opus-4-7). Model interpretation can shift across versions without any prompt change.
2. **Quarterly cadence** (every 90 days from the last run). Catches drift even if the model version is stable.
3. **Material edit to the agent prompt or the baseline**. Any change to either side invalidates the comparability of prior deltas.

The re-baseline produces a new run record with a new `prompt_sha` and `fixture_set_sha`, and the report compares against the prior run.

### CI Cost Projection

The v1 spike consumed $1.20 USD for 60 API calls (10 fixtures × 2 variants × 3 runs) at sonnet-4-6 rates as of 2026-05-03. Token counts were estimated from a 4-chars-per-token heuristic; the cost figure is therefore not authoritative. Production cost projections must use measured `usage` from the API response.

If this methodology graduates to CI, the projected cost per PR cadence is:

- Per run: ~60 API calls × ~5,000 tokens/call ≈ 300K tokens ≈ $1-3 USD per run at current rates.
- Per month: 60 PRs × $2 = $120/month at the project's current PR cadence.
- Per agent: linear scaling. Adding the analyst agent doubles cost.

These projections are illustrative. CI graduation requires a measured-usage projection in the graduating-issue's PR description, not this heuristic estimate.

### Worked Example: Security Agent v1 Calibration

This subsection records the actual numbers from the spike run `20260503T165136Z-84f918a9` (model: `claude-sonnet-4-6`, date: 2026-05-03). The numbers are reproduced verbatim from `evals/security-spike/reports/20260503T165136Z-84f918a9/REPORT.md`.

| Metric | Value |
|---|---|
| Agent recall | 25.0% |
| Baseline recall | 16.7% |
| Signed delta (agent − baseline) | +8.3pp |
| 95% bootstrap CI on delta | [-0.20, +0.31] |
| Flakiness | true (F003 excluded) |
| Errors | 0 |
| Estimated cost | $1.20 USD |
| Wall clock | 11 minutes |

**Per-fixture pass rates** (averaged across N=3 runs):

| Fixture | Verdict | Agent | Baseline | Note |
|---|---|---|---|---|
| F001 | IDENTIFY (CWE-22) | 0.50 | 0.00 | Agent identifies path traversal; baseline misses CWE. |
| F002 | IDENTIFY (STRIDE multi) | 0.50 | 0.50 | Tied. The agent-discriminating intent failed on this fixture. |
| F003 | IDENTIFY (CWE-200) | 0.17 | 0.00 | Flaky; excluded from delta. Agent partially correct. |
| F004 | IDENTIFY | 0.50 | 0.00 | Agent wins verdict; partial CWE match. |
| F005 | OK | 0.00 | 1.00 | **Agent over-identifies.** Baseline correctly says OK; agent flags an issue that is not present. |
| F006-F010 | OK / ESCALATE | 0.00 | 0.00 | Both wrong. Corpus is too hard on this slice. |

**Decision per criteria**: `keep-as-audit`. The signed delta is positive (+8.3pp) but the 95% CI [-0.20, +0.31] spans zero, so the experiment cannot reject the null hypothesis of no agent benefit at the 95% level. Flakiness is true (F003 excluded). No methodology flaw was discovered.

**Minimum detectable effect**: with N=10 paired observations, the experiment can reliably detect only large effects (delta > approximately 0.30). The +0.083 observed is well below that threshold. This ADR therefore does NOT claim "no difference between agent and baseline." It claims the experiment lacks statistical power to distinguish the observed +8.3pp from no effect. The recommended next step for any future agent measured this way is to expand the corpus before drawing conclusions.

**Differential diagnosis** for the delta-near-zero result:

1. *Agent adds no value over baseline for this task.* Possible. F005 (agent over-identifies) is direct evidence that the agent's specialization sometimes hurts.
2. *Baseline is too specific.* Unlikely. The baseline is a generic LLM prompt without security vocabulary.
3. *Corpus is too easy.* Unlikely. Both variants score near zero on F006-F010.
4. *Corpus is too hard.* Likely on F006-F010. Likely contributor to the wide CI.

The reading is: the corpus is too small to draw a strong conclusion, the agent shows a small positive signal on the easier IDENTIFY fixtures, and the agent over-identifies on at least one OK fixture. The right next step is to expand the corpus, not to scrap the agent.

### Cadence Trigger After This Spike

The next eval run for the security agent is triggered on:

1. The next Anthropic model version bump on or after 2026-05-03.
2. 2026-08-03 (90 days from this run), whichever first.
3. Any material edit to the security agent prompt or the baseline.

## Considered Options

### Option 1: LLM-as-Judge as the Gated Signal

Use an LLM evaluator to score agent vs. baseline outputs against a rubric.

| Aspect | Assessment |
|---|---|
| Pros | Captures advice quality; flexible scoring rubric; not limited to pattern-matchable assertions. |
| Cons | Confounds two probabilistic systems; judge drift is indistinguishable from agent drift; cost per run is roughly doubled. |
| Why not chosen | The gated signal must be deterministic. LLM-as-judge survives as an advisory sidecar only. |

### Option 2: Golden Corpus / Large-N Evaluation

Maintain a large corpus (hundreds of fixtures) of known-correct input/output pairs. Compare agent output against the corpus.

| Aspect | Assessment |
|---|---|
| Pros | High statistical power; strong regression detection; closer to industry research standard. |
| Cons | High construction and maintenance cost; brittle to model behavior changes; cost per run scales linearly. |
| Why not chosen | Premature for v1. ADR-057 already rejected golden corpus for the same scale reasons. Consistency with ADR-057's framing keeps both ADRs simple. The methodology can evolve toward golden corpus once a per-agent baseline exists. |

### Option 3: Single Global Delta Threshold

Define one number ("agent must beat baseline by X percentage points") and apply it to every agent.

| Aspect | Assessment |
|---|---|
| Pros | Simple. One number, one rule. |
| Cons | Over-fits to whichever agent sets the number; produces false confidence on the next agent measured. |
| Why not chosen | Rejected. Per-agent calibration is the right call. The decision criteria use "CI lower bound > 0," not a single magic delta. |

### Option 4: Skip Baseline; Score Against Absolute Target

Score agent recall against an absolute target (e.g., "agent must achieve 80% recall").

| Aspect | Assessment |
|---|---|
| Pros | Simple. No baseline maintenance. |
| Cons | Absolute targets are unfalsifiable when corpus difficulty is unknown. A 60% target is meaningless if the corpus is too hard for any prompt. |
| Why not chosen | Paired comparison against a deliberately-naive baseline isolates the prompt-specialization effect. Absolute targets cannot. |

### Option 5: Agent-vs-Baseline With Deterministic Recall (Chosen)

Run the agent and a deliberately-naive baseline against the same held-out corpus at N=3 and temperature=0. Compute paired-bootstrap CI on the recall delta. Apply per-agent calibration via the decision criteria.

| Aspect | Assessment |
|---|---|
| Pros | Deterministic gated signal; per-agent calibration; survivorship-bias-aware; honest about small-N regimes; works on the v1 spike. |
| Cons | Limited to deterministic-scorable agents; does not capture advice quality on the gated path; small-N regime requires honest CI reporting. |
| Why chosen | The methodology produces a usable signal at the v1 spike's scale, distinguishes itself cleanly from ADR-057, and has an honest exit path (`scrap`). |

## Consequences

### Positive

- Agent specialization claims now have an empirical validation path.
- Methodology is reproducible and version-controlled.
- Per-agent calibration prevents over-fitting a global threshold.
- The `scrap` outcome with archive + supersede consequences keeps the methodology honest.
- Cost is bounded (~$1-3 per run at v1 scale).

### Negative

- Limited to deterministic-scorable agents at v1.
- Small-N (10 fixtures) regime cannot detect small effects (< ~0.30 delta).
- Baseline maintenance is a recurring cost. Edits to the baseline invalidate prior deltas.
- Methodology is offline-only. No CI gate yet.

### Neutral

- LLM-as-judge survives as advisory only.
- ADR-057 remains the authority for prompt-edit regression. ADR-058 is the authority for agent-vs-baseline efficacy.
- Future agents may reveal that this methodology does not transfer; that finding is itself signal worth recording (via `scrap` and a successor ADR).

## Confirmation

### Enforced (automated gates)

| Rule | Enforced By | Mechanism |
|---|---|---|
| Fixtures must declare `schemaVersion: 1` | `eval-agent-vs-baseline.py` FixtureValidator | Raise `SchemaVersionError`, exit 2 |
| Fixtures must declare valid `provenance` | FixtureValidator | Reject value outside allowed set |
| Real third-party secrets rejected at ingest | FixtureValidator | Exit 2 with offending fixture id |
| Temperature = 0 on every API call | AnthropicAPIAdapter | Hard-coded in adapter |
| Idempotency on (fixture_id, variant, run_index) | RunPersistence | Raise `DuplicateRunError`, exit 1 |
| Flakiness > 30% halts spike | ReportAggregator | Exit 1 with structured message |
| Per-fixture flakiness contingency rerun at N=5 | ReportAggregator | First detection triggers rerun |

### Not Enforced (architect / reviewer judgment)

| Rule | Why Not Automated | Mitigation |
|---|---|---|
| Baseline is deliberately naive | Requires linguistic judgment | Architect review on every baseline edit |
| Decision verdict (graduate / audit / scrap) | Requires interpretation | Architect-tier reviewer ratifies verdict; SLA fallback to `keep-as-audit` |
| Re-baseline cadence honored | Scheduling concern | Manual cadence; future cron job |
| Cost projection accuracy | Heuristic vs. measured | CI graduation requires measured `usage` |

## Reversibility Assessment

| Criterion | Assessment |
|---|---|
| Rollback capability | Methodology can be dropped without affecting agents or other tests |
| Vendor lock-in | Uses Anthropic API (already a project dependency) |
| Exit strategy | Revert to no empirical eval, or evolve to golden corpus, or supersede with successor ADR |
| Legacy impact | None. Additive to ADR-057. |
| Data migration | Fixtures, run records, and reports are JSON; portable |

**Reversal triggers**: if methodology produces unstable signals across the next two model bumps, or if maintenance cost exceeds the value of the comparisons produced. In either case, the ADR is superseded with a successor that explains what was tried and what would be tried next.

## Vendor Lock-in Assessment

**Dependency**: Anthropic API (sonnet-4-6 and successors).
**Lock-in Level**: Low.

### Lock-in Indicators

- Standard request/response shape; not Anthropic-proprietary.
- Token counts are estimated; real `usage` field is in the response but not yet relied on.
- Fixtures and run records are plain JSON.

### Exit Strategy

- **Trigger conditions**: Anthropic API pricing changes materially, or another provider matches sonnet-4-6's quality at lower cost.
- **Migration path**: replace `_anthropic_api.py` with a provider-neutral adapter; the rest of the runner is provider-agnostic.
- **Estimated effort**: ~1 engineer-day to swap the adapter.
- **Data export**: fixtures and run records are already in portable JSON.

### Accepted Trade-offs

The Anthropic dependency is already paid by ADR-057. Adding ADR-058 does not deepen the lock-in.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|---|---|---|---|
| ADR-057 | Complementary | Add cross-reference noting ADR-058 covers the orthogonal between-subjects question | Low. Follow-up issue. |
| ADR-023 | Complementary | None required | Low |
| ADR-010 | Complementary | None required | Low |
| `evals/security-spike/` | Source artifact | Status preserved at `proposed` until verdict ratified | Low |
| Future agent authors | Direct | Apply this methodology before claiming agent specialization helps | Low |

## Related Decisions

- [ADR-057](ADR-057-prompt-behavioral-evaluation.md): Prompt-edit regression validation. Different question (before/after on the same prompt). Complementary, not overlapping.
- [ADR-023](ADR-023-quality-gate-prompt-testing.md): Structural validation for quality gate prompts. Structural and behavioral evals each serve a distinct purpose.
- [ADR-010](ADR-010-quality-gates-evaluator-optimizer.md): Quality gate patterns. Agent-vs-baseline efficacy is a new application of the quality-gate concept, scoped to the offline path.

## References

- [Issue #1854](https://github.com/rjmurillo/ai-agents/issues/1854): source issue for the spike and this ADR.
- [REQ-004](../specs/requirements/REQ-004-agent-eval-harness-spike.md): requirements (including AC-6 ADR contract).
- [DESIGN-004](../specs/design/DESIGN-004-agent-eval-harness-spike.md): runner design.
- [TASK-004](../specs/tasks/TASK-004-agent-eval-harness-spike.md): task plan.
- `evals/security-spike/reports/20260503T165136Z-84f918a9/REPORT.md`: worked-example numbers.
- `scripts/eval/eval-agent-vs-baseline.py`: runner.
- `.agents/critique/ADR-058-debate-log.md`: architect-led multi-perspective review.
