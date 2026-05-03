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

### What This Methodology Measures (and What It Does Not)

This methodology measures **specialization value**: does the agent's curated content (system prompt, role, instructions) add lift over a generic prompt against the same model on the same fixtures? The spike's two variants are both **agent-form**:

| Variant | Form | Content |
|---|---|---|
| `agent` | subagent dispatch with system prompt | the agent's curated system prompt |
| `baseline` | subagent dispatch with system prompt | a deliberately naive system prompt with no domain vocabulary |

A positive `graduate-to-CI` verdict from this methodology proves the **content** is useful. It does **not** prove the **form** (subagent dispatch with restricted tools, separate model invocation, isolation from parent context) is the right delivery vehicle for that content.

**Out of scope for this ADR**: the agent-vs-skill question — would the same content delivered as a [skill](../../.claude/skills/) loaded into the parent's context produce equivalent recall, at lower cost (one model call instead of two) and without the subagent-isolation complexity (e.g., the 1M-context bug tracked at anthropics/claude-code#55694)? That is a **form-factor** comparison and requires a separate methodology with a third variant `skill` (parent reads `SKILL.md`, reasons inline, scored against the same fixtures). Until that methodology is built and run, a positive verdict here justifies investing in the **content**, not necessarily in the **agent form**.

A future ADR is expected to cover form-factor evaluation. Tracked at [#1875](https://github.com/rjmurillo/ai-agents/issues/1875).

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

This subsection records the actual numbers from the spike run `20260503T165136Z-84f918a9` (model: `claude-sonnet-4-6`, date: 2026-05-03). The numbers are reproduced verbatim from `evals/_archive/security-spike-20260503T165136Z-84f918a9/reports/20260503T165136Z-84f918a9/report.json` (archived per the scrap verdict) after the verdict-extraction regex correction (commit `f0bfec3a`) and re-scoring (commit `8f1e5342`).

| Metric | Value |
|---|---|
| Agent recall | 25.0% |
| Baseline recall | 50.0% |
| Signed delta (agent − baseline) | −25.0pp |
| 95% bootstrap CI on delta | [−0.7273, +0.1538] |
| Flakiness | true (F003 excluded) |
| Errors | 0 |
| Estimated cost | $1.20 USD |
| Wall clock | 11 minutes |

**Per-fixture pass rates** (averaged across N=3 runs):

| Fixture | Verdict | Agent | Baseline | Note |
|---|---|---|---|---|
| F001 | IDENTIFY (CWE-22) | 0.50 | 0.00 | Agent identifies path traversal; baseline misses CWE. Agent wins. |
| F002 | IDENTIFY (STRIDE multi) | 0.50 | 1.00 | Baseline now wins after regex fix; baseline emits the verdict token cleanly while agent's verbose response only partially matches assertions. |
| F003 | IDENTIFY (CWE-200) | 0.17 | 0.00 | Flaky; excluded from delta. Agent partially correct. |
| F004 | IDENTIFY | 0.50 | 0.00 | Agent wins verdict; partial CWE match. |
| F005 | OK | 0.00 | 1.00 | **Agent over-identifies.** Baseline correctly says OK; agent flags an issue that is not present. |
| F006 | OK / ESCALATE | 0.00 | 0.00 | Both wrong. |
| F007 | OK / ESCALATE | 0.00 | 1.00 | Baseline wins. Baseline emits clean verdict; agent's verbose narrative fails to lead with a verdict token. |
| F008 | OK / ESCALATE | 0.00 | 1.00 | Baseline wins. Same pattern as F007. |
| F009 | OK / ESCALATE | 0.00 | 0.00 | Both wrong. |
| F010 | OK / ESCALATE | 0.00 | 1.00 | Baseline wins. Same pattern as F007/F008. |

**Decision per criteria**: `scrap`. The signed delta is negative (−25.0pp); the 95% CI [−0.7273, +0.1538] does not have a positive lower bound; flakiness is true. Two of the three `graduate-to-CI` criteria are decisively failed (recall delta > 0 and CI lower bound > 0). Per the decision criteria, this triggers the `scrap` verdict.

**Correction note**: The original report (committed in `d9c88096`) recorded the verdict as `keep-as-audit` based on `baseline_recall=16.7%` and `recall_delta=+8.3pp`. Those numbers were generated under a buggy verdict-extraction regex that failed to match markdown-bold verdicts (`**OK**`, `**ESCALATE**`). The bug was fixed in commit `f0bfec3a` and the existing run data was re-scored in `8f1e5342`. The corrected numbers above are authoritative.

**Minimum detectable effect**: with N=10 paired observations, the experiment can reliably detect effects of magnitude approximately 0.30 or larger. The observed magnitude of −0.250 is within that detection band. The wide CI [−0.7273, +0.1538] reflects high per-fixture variance (some fixtures cleanly favor agent, others cleanly favor baseline) rather than insufficient sample size for the effect magnitude. The CI's positive arm (+0.1538) does not exceed the detection-band magnitude either, so the experiment does not support a positive-direction conclusion in any direction.

**Differential diagnosis** for the negative-delta result:

1. *Agent's verdict-token emission discipline is worse than baseline's.* Most likely. On the four OK/ESCALATE fixtures where baseline wins (F005, F007, F008, F010), the baseline's terse direct answer leads with the verdict token; the agent's verbose narrative response often buries or fails to produce the expected token format. This is a real finding about the agent prompt's output style, not a corpus problem.
2. *Agent over-identifies on negative cases.* Confirmed on F005. The agent flags an issue that is not present; the baseline correctly says OK. The agent's specialization in detection appears to lower its specificity.
3. *Agent wins on positive-detection fixtures.* Confirmed on F001 and F004. The agent's CWE-vocabulary specialization helps when the assertion specifically rewards CWE identification.
4. *Corpus is too easy for baseline.* The baseline scores 50% on this corpus, indicating the OK/ESCALATE fixtures are closer to commodity LLM-recognition than to specialized security analysis. This is itself a finding: parts of the security-agent's domain may not require security specialization.

**Scope reminder**: this verdict applies to the security agent's *content* (system prompt, role, instructions) compared to a deliberately naive content baseline against the same model on this corpus. It does not address the *form-factor* question (whether the same content delivered as a skill in the parent's context would behave differently). The form-factor question requires a separate methodology with a third variant; see "What This Methodology Measures (and What It Does Not)" near the top of this ADR.

### Cadence Trigger After This Spike

Per the `scrap` verdict above, the security agent's spike is **not** scheduled for re-run on the standard cadence. The corpus and run dir at `evals/security-spike/` are archived to `evals/_archive/security-spike-20260503T165136Z-84f918a9/` (corpus and reports only — the runner code is preserved at `scripts/eval/eval-agent-vs-baseline.py` because the methodology is intact and reusable for future agents).

The next application of this methodology is expected to target a different agent (analyst, qa, or architect) on a fresh corpus. That run will use the corrected runner and produce the methodology's second data point. Until that second data point exists, the methodology is supported by one application that produced a `scrap` verdict due to verdict-token-emission discipline issues in the security agent prompt rather than a flaw in the methodology itself.

**Note on AC-5 divergence**: REQ-004 AC-5's `scrap` consequence text states "the methodology ADR is marked `status: superseded` with a successor ADR documenting the methodology flaw." That text assumed the scrap was triggered by a methodology flaw discovered during the spike. In this case the scrap was triggered by a scoring-engine implementation bug (a regex that failed to match markdown-bold verdicts) which has been fixed by commit `f0bfec3a`. The methodology itself was not flawed. Therefore this ADR keeps `status: proposed` and the runner code is preserved. A follow-up issue will track the corresponding clarification to REQ-004 AC-5.

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
| `evals/security-spike/` | Source artifact | Archived to `evals/_archive/security-spike-20260503T165136Z-84f918a9/` per scrap verdict (Path 2: corpus archived, runner preserved) | Low |
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
- `evals/_archive/security-spike-20260503T165136Z-84f918a9/reports/20260503T165136Z-84f918a9/report.json`: authoritative worked-example numbers (post-rescore; archived per scrap verdict).
- `evals/_archive/security-spike-20260503T165136Z-84f918a9/reports/20260503T165136Z-84f918a9/REPORT.md`: worked-example markdown narrative (post-rescore; archived per scrap verdict).
- `scripts/eval/eval-agent-vs-baseline.py`: runner.
- Commit `f0bfec3a`: fix(eval): extract markdown-formatted verdicts in scoring engine.
- Commit `8f1e5342`: fix(eval): rescore runs with corrected verdict regex.
- `.agents/critique/ADR-058-debate-log.md`: architect-led multi-perspective review (original ratification).
- `.agents/critique/ADR-058-amendment-debate-log.md`: architect-led multi-perspective review of inflight amendments (scope clarification + rescore verdict-flip).
- [Issue #1875](https://github.com/rjmurillo/ai-agents/issues/1875): tracker for follow-on form-factor methodology ADR.
