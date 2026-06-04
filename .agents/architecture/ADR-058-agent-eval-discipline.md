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

### v1 Invalidation (BOTH committed v1 verdicts retracted)

The v1 spike (`20260503T165136Z-84f918a9`, archived at `evals/_archive/security-spike-20260503T165136Z-84f918a9/`) produced two verdicts in sequence: an original `keep-as-audit` (+8.3pp) and a bot-flipped `scrap` (-25.0pp) after a verdict-extraction regex fix. **Both verdicts are invalid.** They were measurement artifacts of an asymmetric experimental design, not measurements of agent specialization value.

A four-agent diagnostic review (`analyst`, `critic`, `independent-thinker`, `security`) converged on the diagnosis at `.agents/critique/SPIKE-1854-methodology-diagnosis.md`. The root cause: the verdict scorer checks for one of three tokens at the start of the response (`IDENTIFY|OK|ESCALATE`), but only the **baseline** was instructed to produce that vocabulary. The agent's system prompt teaches a different verdict vocabulary (`[PASS]/[FAIL]/REJECTED/DO NOT MERGE/[BLOCKED]`) and never mentions the scorer's tokens. Result: the agent received a structural shutout: 0 of 30 verdict-assertion passes across all v1 runs.

The original `keep-as-audit` verdict was an artifact of the buggy regex equally suppressing both variants' markdown-bold verdicts. The flipped `scrap` was an artifact of fixing the regex for the baseline only (the agent never produced the relevant tokens in any form, raw or markdown). Neither delta reflects agent specialization value.

**v1 numbers, retained as a record of what the rigged comparison produced** (do NOT cite these as evidence of agent quality):

| Reading | Agent recall | Baseline recall | Signed delta | Verdict |
|---|---|---|---|---|
| Original (broken regex) | 16.7% | 8.3% | +8.3pp | `keep-as-audit` (invalid) |
| Re-scored (fixed regex, still rigged contract) | 25.0% | 50.0% | -25.0pp | `scrap` (invalid) |

The v1 archive is preserved as evidence at `evals/_archive/security-spike-20260503T165136Z-84f918a9/`. Future readers should treat that directory as a teaching example of what an asymmetric output-shape contract looks like in practice.

The methodology fix landed at commit `61f1b6b8`: a shared `OUTPUT_SHAPE_SUFFIX` is now appended to the **user message** of both variants. The v2 re-run at commit `5f8fd96f` (RUN_ID `20260503T182553Z-eaa08f8d`) produces the worked example below.

### Experimental Design Symmetry (Normative)

The agent variant and the baseline variant **MUST** receive identical user messages. Only the system prompt MAY differ between variants. This is the load-bearing experimental control that makes the comparison a measurement of system-prompt content rather than of any other variable.

**Canonical implementation**: `OUTPUT_SHAPE_SUFFIX` in `scripts/eval/eval-agent-vs-baseline.py`. The suffix is appended to the fixture's input string before the user message is constructed for either variant. The runner's `_build_prompt(variant, agent_prompt, fixture_input)` function MUST construct the user message identically for both variants. The current implementation is:

```python
user_prompt = fixture_input + OUTPUT_SHAPE_SUFFIX
if variant == "agent":
    return agent_prompt, user_prompt
return BASELINE_PROMPT, user_prompt
```

`BASELINE_PROMPT` is now a role-neutralization prompt only (`"Review the following input."`). The output-shape contract is no longer in the baseline's system prompt; it is in the user message that both variants receive.

**Symmetry checks the runner enforces** (the runner MUST hold all six identical between variants on every run):

| Symmetry property | What is held identical | Where enforced |
|---|---|---|
| Model | `claude-sonnet-4-6` for both variants | `AnthropicAPIAdapter` model field |
| Temperature | `temperature=0` for both variants | Hard-coded in `AnthropicAPIAdapter` |
| Fixture input | Same `fixture.input` string passed to both variants | `_build_prompt` accepts one `fixture_input` argument |
| Retry policy | Same retry handler wraps both variants' API calls | `AnthropicAPIAdapter` retry branch |
| Scoring engine | `_scoring_engine.py::VerdictScorer` and `RegexScorer` applied to both variants' raw responses | `_scoring_engine.py` |
| Output-shape contract | `OUTPUT_SHAPE_SUFFIX` appended to both variants' user message | `_build_prompt` |

A change to any of these MUST be documented as a methodology amendment. A change that breaks symmetry (for example, applying `OUTPUT_SHAPE_SUFFIX` to only one variant) MUST be rejected at code review and CI.

**Why this is normative.** The v1 spike violated symmetry on the output-shape contract: only the baseline was told what tokens the scorer would check. The result was a structural shutout for the agent that two committed verdicts misread as a measurement. The symmetry requirement is the methodology's primary defense against that class of error. It is not negotiable for offline runs and is a precondition for any future CI graduation.

### Scope

This methodology applies to agents with **deterministic-scorable output**: agents whose responses contain structured verdicts, pattern-matchable identifiers (CWE numbers, STRIDE categories, severity labels), or other content that can be checked against assertions without LLM judgment. Agents with freeform output (open-ended advice, narrative summaries, multi-step plans) require a different methodology not covered by this ADR.

### What This Methodology Measures (and What It Does Not)

This methodology measures **specialization value**: does the agent's curated content (system prompt, role, instructions) add lift over a generic prompt against the same model on the same fixtures? The spike's two variants are both **agent-form**:

| Variant | Form | Content |
|---|---|---|
| `agent` | subagent dispatch with system prompt | the agent's curated system prompt |
| `baseline` | subagent dispatch with system prompt | a deliberately naive system prompt with no domain vocabulary |

A positive `graduate-to-CI` verdict from this methodology proves the **content** is useful. It does **not** prove the **form** (subagent dispatch with restricted tools, separate model invocation, isolation from parent context) is the right delivery vehicle for that content.

**Out of scope for this ADR**: the agent-vs-skill question: would the same content delivered as a [skill](../../.claude/skills/) loaded into the parent's context produce equivalent recall, at lower cost (one model call instead of two) and without the subagent-isolation complexity (e.g., the 1M-context bug tracked at anthropics/claude-code#55694)? That is a **form-factor** comparison and requires a separate methodology with a third variant `skill` (parent reads `SKILL.md`, reasons inline, scored against the same fixtures). Until that methodology is built and run, a positive verdict here justifies investing in the **content**, not necessarily in the **agent form**.

A future ADR is expected to cover form-factor evaluation. Tracked at [#1875](https://github.com/rjmurillo/ai-agents/issues/1875).

**Symmetry requirement** (third measurement boundary): a measurement is only valid when both variants face the same output-shape contract. The v1 spike violated this requirement (only the baseline's system prompt taught the scorer's verdict vocabulary; the agent's system prompt taught a different vocabulary that the scorer rejected). Both v1 verdicts were artifacts of that asymmetry, not measurements of agent quality. v1 is the canonical example of what NOT to do; see the v1 invalidation subsection above and the diagnosis at `.agents/critique/SPIKE-1854-methodology-diagnosis.md`. The symmetry requirement is now codified by the `OUTPUT_SHAPE_SUFFIX` pattern and the symmetry checks above.

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
| `scrap` (methodology flaw) | a methodology flaw is discovered during the spike (the experiment design itself was wrong) | The runner (`scripts/eval/eval-agent-vs-baseline.py` plus its six modules and tests) AND the corpus and run directory are moved to `evals/_archive/<agent>-spike-<RUN_ID>/`. The methodology ADR (this one or its successor) is marked `status: superseded` with a successor ADR documenting the methodology flaw and what would be tried instead. |
| `scrap` (negative or null delta, or fixed bug) | no meaningful delta (CI centered on zero or negative) under a sound, symmetric experimental design, OR an implementation bug that has since been fixed | Only the corpus and run directory are moved to `evals/_archive/<agent>-spike-<RUN_ID>/`. The runner stays in `scripts/eval/` because the methodology is sound and lives on for the next agent. The ADR stays at its prior status (it is NOT superseded). The agent under test loses its eval; the methodology-as-code is preserved. |
| `halt-due-to-flakiness` | flakiness > 30% of fixtures after the contingency rerun (per AC-10) | The methodology produces no graduate / audit / scrap verdict on this run. Investigate variance source (control test: same fixture × same variant × N=10 runs to quantify temperature=0 non-determinism on long context). Consider corpus expansion (N≥30) before next attempt. **Do NOT graduate to CI without resolving the variance.** Underlying numbers may be reported as informational but are non-normative. |

These criteria are normative. The ADR does not soften "scrap" into "needs more work" or "halt-due-to-flakiness" into a soft pass. Each outcome is a real outcome and the methodology treats it as such. `halt-due-to-flakiness` is in particular not a path to graduation; it is a halt that requires variance investigation before another verdict-grade run is attempted.

**`scrap` has two cases (mirrors REQ-004 AC-5).** The two `scrap` rows above split the outcome by cause, matching REQ-004 AC-5's two-cause table (issue #2389, PR #2358). The split is load-bearing: only the methodology-flaw case archives the runner and supersedes the ADR; the negative-or-null-delta or fixed-bug case archives the corpus and run directory only, leaves the runner in `scripts/eval/`, and keeps the ADR at its prior status. The distinction protects the methodology-as-code from being thrown away when the cause is a weak agent or a since-fixed bug rather than a broken experiment design.

**N-aware halt threshold (Issue #1878)**: the halt fires when the flaky-fixture count reaches `max(floor(0.30 * N) + 1, min(5, N // 2))`, so the strict "more than 30%" gate (a flaky share of exactly 30% does NOT halt) governs at large N while a small-N floor keeps a couple of flaky fixtures from halting a tiny corpus (at N=10 the floor is 5, so 4 flaky no longer halts). At N=30 the gate halts at 10 (9 of 30 is exactly 30% and continues). `ReportAggregator` also exposes a flag-and-continue mode that records the crossing without halting; see `scripts/eval/_report_aggregator.py:_flaky_halt_count`.

### Decision Owner and SLA

The architect role owns the graduate / audit / scrap / halt-due-to-flakiness decision via Tier 3 architecture review. The decision MUST be ratified in PR review by an architect-tier reviewer before the verdict is committed.

**SLA fallback**: if no architect-tier reviewer ratifies the verdict within 5 business days of the spike report's PR opening, the decision defaults to `keep-as-audit`. The runner remains offline-only and the next-quarter review serves as the next decision point. This prevents indefinite limbo without forcing a premature `graduate-to-CI` or `scrap`. The fallback does NOT apply to `halt-due-to-flakiness` runs: those require explicit variance investigation before another verdict-grade attempt is made; the SLA fallback cannot upgrade a halt to an audit.

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

### Worked Example: Security Agent v2 Calibration (halt-due-to-flakiness)

This subsection records the actual numbers from the v2 spike run `20260503T182553Z-eaa08f8d` (model: `claude-sonnet-4-6`, date: 2026-05-03, methodology version 2 per fix commit `61f1b6b8`). The numbers are reproduced verbatim from `evals/security-spike/reports/20260503T182553Z-eaa08f8d/report.json`. The v2 run supersedes the v1 run `20260503T165136Z-84f918a9` (now archived at `evals/_archive/security-spike-20260503T165136Z-84f918a9/`) whose comparison was structurally rigged. See the v1 invalidation subsection above and the diagnosis at `.agents/critique/SPIKE-1854-methodology-diagnosis.md`.

| Metric | All fixtures | Non-flaky subset (F004, F006-F010) |
|---|---|---|
| Agent recall | 78.6% | 100.0% |
| Baseline recall | 40.5% | 57.1% |
| Signed delta (agent − baseline) | **+38.1pp** | **+42.9pp** |
| Flakiness | true (40% > 30% halt threshold per AC-10) | false |
| Errors | 0 | 0 |
| Estimated cost | $0.89 USD | (subset of all-fixture cost) |
| Wall clock | ~10 minutes | (subset of all-fixture wall clock) |

**Flaky fixtures**: F001, F002, F003, F005 (4 of 10 = 40% > 30% halt threshold).

**Per-fixture pass rates** (3 runs each, raw):

| Fixture | Verdict | Agent (per run) | Baseline (per run) | Flaky | Note |
|---|---|---|---|---|---|
| F001 | IDENTIFY (CWE-22) | 1.00, 0.50, 0.50 | 0.00, 0.00, 0.00 | yes | Verdict varied across runs: ['IDENTIFY', 'ESCALATE', 'ESCALATE']. Both verdicts defensible on a path-traversal fixture. Agent dominates baseline regardless. |
| F002 | IDENTIFY (STRIDE multi) | 0.50, 1.00, 0.00 | 0.50, 0.50, 0.50 | yes | Verdict varied across runs: ['ESCALATE', 'IDENTIFY', 'ESCALATE']. Same pattern. |
| F003 | IDENTIFY (CWE-200) | 0.50, 0.50, 0.00 | 0.00, 0.00, 0.00 | yes | Verdict consistent; regex assertion flaky (likely CWE-string variance). |
| F004 | IDENTIFY | 1.00, 1.00, 1.00 | 0.00, 0.00, 0.00 | no | Agent perfect; baseline structural miss. Content-specialization wins. |
| F005 | OK | 1.00, 1.00, 1.00 | 1.00, 1.00, 0.00 | yes | Agent perfect; baseline flaky on third run. |
| F006 | OK / ESCALATE | 1.00, 1.00, 1.00 | 0.00, 0.00, 0.00 | no | Agent perfect; baseline structural miss. |
| F007 | OK / ESCALATE | 1.00, 1.00, 1.00 | 1.00, 1.00, 1.00 | no | Both perfect. Commodity-LLM-recognizable. |
| F008 | OK / ESCALATE | 1.00, 1.00, 1.00 | 1.00, 1.00, 1.00 | no | Both perfect. |
| F009 | OK / ESCALATE | 1.00, 1.00, 1.00 | 1.00, 1.00, 1.00 | no | Both perfect. |
| F010 | OK / ESCALATE | 1.00, 1.00, 1.00 | 1.00, 1.00, 1.00 | no | Both perfect. |

**Decision per criteria**: **`halt-due-to-flakiness`**. Per AC-10, flakiness on 40% of fixtures (4/10, threshold 30%) halts the spike. The methodology cannot conclude `graduate-to-CI`, `keep-as-audit`, or `scrap` on this run. The bootstrap CI is intentionally not computed (`bootstrap_ci_95: null` in `report.json`); the runner short-circuits CI computation when the flakiness halt fires because the halt invalidates the verdict regardless of the CI shape. Underlying numbers above are reported as informational signal but are non-normative.

**Variance pattern**:

- F001 verdicts across 3 agent runs: `['IDENTIFY', 'ESCALATE', 'ESCALATE']`. Two defensible answers to the same path-traversal fixture (find-the-issue vs needs-escalation).
- F002 verdicts across 3 agent runs: `['ESCALATE', 'IDENTIFY', 'ESCALATE']`. Same shape on a STRIDE multi-category fixture.
- F003 / F005: verdict consistent; regex-string variance (CWE-string formatting differs across runs).
- **Hypothesis**: Anthropic API at temperature=0 is not strictly deterministic on long context (the agent's system prompt is ~8K tokens). Variance manifests on borderline cases where multiple defensible verdicts exist.

**Statistical power note**: with 30 paired observations (10 fixtures × 3 runs), the experiment can reliably detect effects of magnitude ~0.30 or larger. The observed +38.1pp all-fixture delta and +42.9pp non-flaky-subset delta both exceed this band. The directional signal is strong and consistent with the analyst's pre-rerun manual-mapping estimate (~0.80 agent recall under a fair contract). However, statistical power is not the same as verdict; AC-10 halt is AC-10 halt. The signal is informative, not normative.

**Differential diagnosis** for the v2 result:

1. *Agent specialization is real on positive-detection fixtures.* Confirmed on F001, F004, F006: agent identifies CWE patterns the baseline misses. CWE vocabulary in the agent's system prompt produces lift.
2. *Agent and baseline tie on commodity-recognizable cases.* F007, F008, F009, F010 score 1.00 on both variants. Parts of the security-agent's domain are recognizable to a naive prompt under a fair output-shape contract.
3. *Borderline-verdict fixtures are flaky under temperature=0 + long context.* F001 and F002 show the agent disagreeing with itself between defensible verdicts across runs. This is a model-side non-determinism finding, not an agent-content finding.
4. *The +38pp gain is content-driven, not vocabulary-recognition-driven.* Both variants receive the identical user message including `OUTPUT_SHAPE_SUFFIX`. The agent's system prompt does not contain the suffix's vocabulary. The gain on F004 / F006 is from CWE pattern identification, not from priming.

**Comparison with v1 (record of what changed)**:

| Reading | Agent recall | Baseline recall | Signed delta | Verdict |
|---|---|---|---|---|
| v1 original (broken regex) | 16.7% | 8.3% | +8.3pp | `keep-as-audit` (invalid; rigged contract) |
| v1 re-scored (fixed regex, still rigged contract) | 25.0% | 50.0% | -25.0pp | `scrap` (invalid; rigged contract) |
| **v2 (symmetric contract)** | **78.6%** | **40.5%** | **+38.1pp** | **`halt-due-to-flakiness`** (per AC-10) |

The v2 numbers point opposite to the v1 re-scored numbers. The reversal is fully explained by the symmetry fix in commit `61f1b6b8`: the v1 comparison forced the agent to compete on a vocabulary it was never told about; the v2 comparison gives both variants the same output-shape contract.

**Scope reminder**: this result applies to the security agent's *content* (system prompt, role, instructions) compared to a deliberately naive content baseline against the same model on this corpus. It does not address the *form-factor* question (whether the same content delivered as a skill in the parent's context would behave differently). The form-factor question requires a separate methodology with a third variant; see "What This Methodology Measures (and What It Does Not)" near the top of this ADR.

### Cadence Trigger After This Spike

Per the `halt-due-to-flakiness` verdict above, the next trigger for this agent is **not** the standard quarterly cadence. The next trigger is variance investigation followed by corpus expansion:

1. **Variance investigation (control test)**: same fixture × same variant × N=10 runs at temperature=0. Quantify the non-determinism. Reference output: a per-fixture variance distribution.
2. **Corpus expansion**: target N≥30 fixtures so that AC-10's percentage threshold (30%) corresponds to a more meaningful absolute count. At N=10, one flaky fixture is 10% of the corpus and three flaky fixtures already exceed the threshold; at N=30, the threshold corresponds to nine fixtures.
3. **Borderline-fixture redesign**: F001 and F002 admit multiple defensible verdicts under the current expected-value spec. Revisit the fixture design so the expected verdict is unambiguous, or accept the ambiguity by widening the assertion (e.g., accept either IDENTIFY or ESCALATE on path-traversal scenarios).

Only after these three steps land may the security agent's spike be re-run for a verdict-grade outcome. The standard cadence triggers (model bump, quarterly, prompt edit) do NOT supersede the variance-investigation gate; they apply once the gate has been cleared.

The runner code at `scripts/eval/eval-agent-vs-baseline.py` is preserved and is at methodology version 2 (commit `61f1b6b8`). The corpus at `evals/security-spike/fixtures/` is preserved. The v1 run dir is archived at `evals/_archive/security-spike-20260503T165136Z-84f918a9/` as evidence of the rigged comparison.

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
- The two-case `scrap` outcome (methodology flaw archives the runner and supersedes the ADR; negative or null delta or fixed bug archives only the corpus and run directory) keeps the methodology honest while preserving sound methodology-as-code.
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
| Flakiness > 30% halts spike (`halt-due-to-flakiness` verdict) | ReportAggregator | Halt verdict with structured message; CI not computed |
| Per-fixture flakiness contingency rerun at N=5 | ReportAggregator | First detection triggers rerun |
| Identical user message between variants (`OUTPUT_SHAPE_SUFFIX` applied to both) | `_build_prompt` | Single user-prompt construction path; no variant-specific suffix |

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
| `evals/security-spike/` (v1) | Source artifact | Archived to `evals/_archive/security-spike-20260503T165136Z-84f918a9/` as evidence of rigged comparison; v1 verdicts retracted | Low |
| `evals/security-spike/` (v2) | Source artifact | Active corpus and run dir under methodology v2 (commit `61f1b6b8`); v2 run `20260503T182553Z-eaa08f8d` produced `halt-due-to-flakiness` | Low |
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
- `evals/security-spike/reports/20260503T182553Z-eaa08f8d/report.json`: authoritative v2 worked-example numbers (current).
- `evals/security-spike/reports/20260503T182553Z-eaa08f8d/REPORT.md`: v2 worked-example markdown narrative.
- `evals/_archive/security-spike-20260503T165136Z-84f918a9/`: v1 archive, preserved as evidence of the rigged comparison.
- `scripts/eval/eval-agent-vs-baseline.py`: runner (methodology v2 per commit `61f1b6b8` (2026-05-03)).
- Commit `61f1b6b8` (2026-05-03): fix(evals): symmetrize verdict-vocabulary contract across variants. The methodology v1->v2 fix.
- Commit `5f8fd96f` (2026-05-03): feat(evals): re-execute spike with fixed methodology; halt-due-to-flakiness. The v2 re-run.
- Commit `f0bfec3a` (2026-05-03): fix(eval): extract markdown-formatted verdicts in scoring engine. (v1 regex fix; correct under the rigged contract; superseded by symmetry fix.)
- Commit `8f1e5342` (2026-05-03): fix(eval): rescore runs with corrected verdict regex. (v1 rescore; superseded.)
- `.agents/critique/SPIKE-1854-methodology-diagnosis.md` (2026-05-03): four-agent diagnostic review establishing v1 invalidation.
- `.agents/critique/ADR-058-debate-log.md` (2026-05-03): architect-led multi-perspective review (original ratification).
- `.agents/critique/ADR-058-amendment-debate-log.md` (2026-05-03): architect-led multi-perspective review of inflight amendments (second amendment, pre-diagnosis).
- `.agents/critique/ADR-058-third-amendment-debate-log.md` (2026-05-03): architect-led multi-perspective review of the third amendment (v1 invalidation, v2 worked example, symmetry requirement, halt-due-to-flakiness outcome).
- [Issue #1875](https://github.com/rjmurillo/ai-agents/issues/1875) (2026-05-03): tracker for follow-on form-factor methodology ADR.
