# ADR Amendment Debate Log: ADR-058 Third Amendment (Methodology Symmetry + v1 Invalidation + v2 Re-run)

## Summary

- **Rounds**: 3
- **Outcome**: Consensus reached
- **Final Status**: amendment approved, applied
- **Date**: 2026-05-03
- **Decision-makers**: architect (this review), critic, independent-thinker, security, analyst, high-level-advisor
- **Subject**: third amendment to ADR-058 on branch `feat/1854-ms-3-spike-decision`

This file is **separate** from `ADR-058-debate-log.md` (the original ratification) and `ADR-058-amendment-debate-log.md` (the second amendment, written before the four-agent diagnostic review). The architect-evidence gate per ADR-033 requires this third amendment debate log on disk before any further ADR write that lands the v1 invalidation, the v2 worked example, the symmetry-requirement subsection, and the new `halt-due-to-flakiness` outcome.

## Trigger

A four-agent diagnostic review (`analyst`, `critic`, `independent-thinker`, `security`) converged independently on the conclusion that **both** committed v1 verdicts (the original `keep-as-audit` at +8.3pp and the bot's flipped `scrap` at -25.0pp) were measurement artifacts of an asymmetric experimental design. The agent's system prompt teaches a different verdict vocabulary (`[PASS]/[FAIL]/REJECTED/DO NOT MERGE/[BLOCKED]`) than the scorer checks (`IDENTIFY|OK|ESCALATE`), and only the baseline was instructed to satisfy the scorer's contract. The agent received a structural shutout: 0 of 30 verdict-assertion passes across all v1 runs.

The fix landed at commit `61f1b6b8`: a shared `OUTPUT_SHAPE_SUFFIX` is now appended to the **user message** of both variants. Only the system prompt differs between variants. The spike was re-executed at commit `5f8fd96f` with RUN_ID `20260503T182553Z-eaa08f8d`. Numbers and report are committed; ADR-058 still narrates the v1 (invalid) numbers.

## Inputs Reviewed

- `.agents/architecture/ADR-058-agent-eval-discipline.md` (current branch state, post-second-amendment)
- `.agents/critique/ADR-058-debate-log.md` (original ratification log)
- `.agents/critique/ADR-058-amendment-debate-log.md` (second amendment log, now superseded by this diagnosis)
- `.agents/critique/SPIKE-1854-methodology-diagnosis.md` (four-agent diagnosis)
- `evals/security-spike/reports/20260503T182553Z-eaa08f8d/report.json` (v2 authoritative numbers)
- `evals/security-spike/reports/20260503T182553Z-eaa08f8d/REPORT.md` (v2 markdown narrative)
- `evals/security-spike/runs/20260503T182553Z-eaa08f8d/runs.jsonl` (v2 raw runs)
- `evals/_archive/security-spike-20260503T165136Z-84f918a9/` (v1 archive, preserved as evidence of the rigged comparison)
- `scripts/eval/eval-agent-vs-baseline.py` (v2 runner with `OUTPUT_SHAPE_SUFFIX` and symmetric `_build_prompt`)
- Commit `61f1b6b8` (methodology fix)
- Commit `5f8fd96f` (v2 re-run)

## Round 1: Position Statements

### Architect Position (this review)

**Verdict on the third amendment**: APPROVED with concrete edit set.

**On the v1 invalidation framing**. The diagnosis is correct. The original v1 measurement violated experimental control: the variants were not given the same task (only the baseline was told what output shape the scorer would check). The 0-of-30 verdict-assertion shutout for the agent is a structural shutout, not a measurement of agent quality. Both v1 verdicts must be retracted. The retraction must be prominent; future readers must not see the v1 numbers without the invalidation context.

**On the symmetry requirement**. The new `OUTPUT_SHAPE_SUFFIX` pattern is the correct fix and must be normative going forward. The principle is broader than this one fix: agent and baseline must receive **identical user messages** so that the only free variable is the system prompt content. The runner must enforce this in code (it now does, in `_build_prompt`), and the ADR must enforce this in writing.

**On the v2 result**. The v2 numbers are honest but the run halted at AC-10 flakiness threshold (4/10 fixtures = 40% > 30%). This means the methodology cannot conclude `graduate-to-CI`, `keep-as-audit`, or `scrap` on this run. The honest verdict is `halt-due-to-flakiness`, a fourth outcome the original ADR did not enumerate but which is implicit in AC-10's halt rule. This must be documented as a first-class outcome in the decision criteria table.

**On the directional signal**. The v2 non-flaky-subset shows agent 100.0% vs baseline 57.1% (+42.9pp). All-fixture shows 78.6% vs 40.5% (+38.1pp). This is consistent with the analyst's pre-rerun manual-mapping estimate (~0.80) and with the independent-thinker's falsifier (positive delta survives the symmetry fix). The v2 signal is large and points opposite to the bot's flipped scrap. But AC-10 halt is AC-10 halt; the signal is informative, not normative.

**On status field**. Architect's recommendation: keep `proposed`. The methodology has now improved through three amendments. The symmetry requirement is a substantive addition, not a cosmetic clarification. A future amendment may further refine it (for example, after the variance investigation). `accepted` should wait until at least one application of the methodology produces a clean (non-halted) verdict. That has not happened yet.

**On scope. The split question (high-level-advisor's framing)**. ADR-058 is now carrying: (1) the basic agent-vs-baseline methodology, (2) the deterministic-only scoring discipline, (3) the per-agent calibration framework, (4) a worked example that has been re-run twice, (5) the form-factor scope clarification (specialization-of-content vs form-factor-value), (6) the symmetry requirement, (7) the v1 invalidation history, (8) the `halt-due-to-flakiness` outcome. That is a lot for one ADR. Architect's view: do not split now. The pieces are still tightly coupled around one core question (does specialized content beat naive content). A split would force readers to chase cross-references for a methodology that is still maturing. Reconsider after the next clean run.

**Architect amendments to the inflight ADR text** (concrete):

1. Add a "v1 Invalidation" subsection prominently early in the Decision section (before the worked example).
2. Add an "Experimental Design Symmetry" subsection in the methodology section. Use MUST language. Document the OUTPUT_SHAPE_SUFFIX pattern as the canonical implementation.
3. Replace the worked example wholesale with v2 numbers from `report.json`. Remove the previous keep-the-old-numbers verdict subsection from the second amendment (those numbers came from the rigged comparison).
4. Add `halt-due-to-flakiness` as a fourth outcome in the decision criteria table.
5. Update the cadence trigger subsection to reflect that the next trigger is variance investigation + corpus expansion, not the quarterly fallback.
6. Add a third paragraph to "What this methodology measures" about the symmetry requirement; cite v1 as the canonical example of what to NOT do.
7. Cross-reference `evals/_archive/security-spike-20260503T165136Z-84f918a9/` as preserved evidence.
8. Preserve the second-amendment scope clarification (specialization vs form-factor), that section is still correct and useful.
9. Preserve the v1 numbers somewhere (in the v1 invalidation subsection, as a "this is what the rigged comparison produced" record).

### Critic Position

**Verdict**: APPROVED.

**Issues raised**:

| Priority | Issue | Disposition |
|---|---|---|
| P0 | "Are we over-rotating because of one bad result and one good result? What if v3 also halts?" | Resolved: the architect's recommendation is `halt-due-to-flakiness` per AC-10, NOT `graduate-to-CI`. The +43pp non-flaky signal is informative and the directional answer is consistent with the analyst's pre-rerun estimate. But the methodology is honest: the AC-10 threshold halts the verdict regardless of which way the underlying signal points. We are not over-rotating; we are recording an honest halt with a strong informational signal. |
| P0 | The v1 numbers MUST be preserved somewhere in the ADR so future readers can see what the rigged comparison produced and why it was wrong. Removing them entirely would erase the lesson. | Resolved: the v1 invalidation subsection retains the v1 numbers explicitly with the invalidation reason. |
| P0 | The worked example numbers MUST match `report.json` exactly. No paraphrasing, no rounding. | Resolved: architect commits to verbatim values from `report.json`: 78.6% / 40.5% / +38.1pp / non-flaky 100.0% / 57.1% / +42.9pp / cost $0.89 / wall ~10 min. |
| P1 | The `halt-due-to-flakiness` outcome must NOT be a soft path for agents to dodge a `scrap` verdict. The AC-10 halt should trigger investigation, not relief. | Resolved: the new row's operational consequence reads "investigate variance source; consider corpus expansion before next attempt; do NOT graduate to CI without resolving the variance." Halt is a halt, not a graduate. |
| P1 | The symmetry requirement must be MUST language, not SHOULD. A SHOULD invites the next variant author to add asymmetric context "just for one run". | Resolved: architect commits to MUST language. |
| P1 | The v1 invalidation must NOT be soft-pedaled as "regex bug." The fix the bot landed in `f0bfec3a` and `8f1e5342` was correct under the rigged contract; the rigging is what made the regex bug a verdict-flipping event. The diagnosis at `.agents/critique/SPIKE-1854-methodology-diagnosis.md` is the authoritative explanation and must be cited. | Resolved: architect's invalidation subsection cites the diagnosis log directly and names the asymmetric output-shape contract as the root cause. |

The critic accepts the third amendment if all six issues are addressed in the final ADR body.

### Independent-Thinker Position

**Verdict**: PROCEED.

**Alternative reading the independent-thinker explored**: could the agent's +38pp gain be an artifact of "the model recognizes its own system prompt's vocabulary appearing in a user-suffix"? In other words: the agent's system prompt teaches one set of terms; the user message now contains an explicit `IDENTIFY|OK|ESCALATE` instruction that does not appear in the agent's system prompt. Could the agent be benefiting from a context-priming effect where seeing the canonical tokens in the user message activates security-relevant attention?

The independent-thinker rejects this reading after the following analysis:

1. **The same suffix is appended to the baseline.** Both variants see the identical user message. Any priming effect from the suffix is shared.
2. **The agent's system prompt does not teach `IDENTIFY|OK|ESCALATE`.** It teaches `[PASS]/[FAIL]/REJECTED`. So the user-message suffix is novel context for the agent, not a self-recognition signal.
3. **The +43pp non-flaky-subset gain is dominated by F004 and F006** (both 1.00 vs 0.00). On those fixtures the agent identifies real CWE patterns the baseline misses. That is a content-specialization effect (CWE vocabulary in the system prompt), not a verdict-token effect.
4. **The flakiness on F001/F002 (verdict varies between IDENTIFY and ESCALATE) is not a self-recognition artifact.** Both verdicts are defensible answers to the same prompt; the variance reflects genuine uncertainty in the agent's classification, not vocabulary confusion.

Falsifier: if the v3 re-run (after corpus expansion or variance investigation) shows the +43pp gain depends on the explicit suffix in the user message, the independent-thinker's reading would be supported. The current evidence does not support it.

**Caveat for the architect**: the independent-thinker accepts the architect's recommendation to NOT split ADR-058. The pieces are still tightly coupled. A split would create a chase-pointer reading experience for a methodology that has not yet produced a clean verdict. After v3 produces a non-halted result (or a second halt that motivates redesign), reconsider.

**Caveat on status field**: the independent-thinker accepts `proposed`. Three substantive amendments in one branch is a methodology in motion. `accepted` would freeze it prematurely.

### Security Position

**Verdict**: APPROVED.

**Checks performed on procedural fairness of the v2 comparison**:

1. **Same model**: both variants invoke `claude-sonnet-4-6`. CONFIRMED in `runs.jsonl` (`model_id` field).
2. **Same temperature**: temperature=0 hard-coded in `AnthropicAPIAdapter` per the original ADR-058. No variant-specific override. CONFIRMED.
3. **Same fixture input**: `_build_prompt(variant, agent_prompt, fixture.input)` constructs `user_prompt = fixture_input + OUTPUT_SHAPE_SUFFIX` in both branches. CONFIRMED at `scripts/eval/eval-agent-vs-baseline.py:344-357`.
4. **Same retry policy**: retry handling is in `AnthropicAPIAdapter`, not in the variant branches. CONFIRMED.
5. **Same scoring engine**: `_scoring_engine.py::VerdictScorer` and `RegexScorer` are applied to both variants' raw responses. CONFIRMED.
6. **Same output-shape contract**: `OUTPUT_SHAPE_SUFFIX` is appended to BOTH variants' user message. CONFIRMED at the same line range. The only difference between variants is the system prompt: agent gets the security agent's full template; baseline gets the role-neutralization prompt `"Review the following input."`.

**Security perspective on the comparison**: the v2 procedure is procedurally fair. The agent's specialization (its system prompt content) competes with baseline's specialization (none) on the same measurable quantity, with the same input, in the same scoring frame. This is the experimental design that should have been there from v1.

**Security view on the v1 archive**: preserving `evals/_archive/security-spike-20260503T165136Z-84f918a9/` is the right call. It documents the rigged comparison as evidence; deleting it would erase the lesson.

**No blocking concerns.**

### Analyst Position

**Verdict**: APPROVED with one statistical-power note.

**On statistical power of the v2 result given the AC-10 halt**:

- N=10 fixtures × 3 runs each = 30 paired observations on each variant.
- The all-fixture signed delta is +38.1pp (large; well above the ~30pp minimum detectable effect at N=10 from prior power analysis).
- The non-flaky subset (N=6) shows an even larger +42.9pp delta.
- The bootstrap CI was not computed in `report.json` (`bootstrap_ci_95: null`) because the AC-10 halt fired before CI computation. This is a runner-side decision: the `report_aggregator` short-circuits on halt-due-to-flakiness because the halt invalidates the verdict.
- Statistical power is high enough that the +38pp directional signal is not noise. But power is not the same as verdict. The variance pattern on F001 (`['IDENTIFY', 'ESCALATE', 'ESCALATE']`) and F002 (`['ESCALATE', 'IDENTIFY', 'ESCALATE']`) shows that the agent's classification on borderline cases is genuinely unstable across runs. That instability is a real finding about the agent under temperature=0 on long context, not a corpus or methodology problem.

**Suggested wording for the variance pattern in the ADR**: "Anthropic API at temperature=0 is not strictly deterministic on long context (the agent's system prompt is ~8K tokens). The variance manifests on borderline cases where multiple defensible verdicts exist. Quantifying this with a control test (same fixture × same variant × N=10 runs) is the recommended next step before another spike attempt."

**On the +42.9pp non-flaky number**: this should be presented as an informational signal, not a verdict-grade number. The non-flaky subset is selected after observing variance; presenting it as the headline would be a soft form of cherry-picking. The headline should be the all-fixture +38.1pp delta with the non-flaky subset as supporting context.

The analyst accepts the architect's worked-example structure.

### High-Level-Advisor Position

**Verdict**: APPROVED with a structural recommendation about ADR shape.

**On scope creep**: the high-level-advisor flagged that ADR-058 has accumulated:

1. The basic agent-vs-baseline methodology (original).
2. The deterministic-only gated signal (original).
3. The per-agent calibration framework (original).
4. A worked example that has been re-run twice (original + second + third amendment).
5. The form-factor scope clarification (second amendment).
6. The symmetry requirement (third amendment).
7. The v1 invalidation history (third amendment).
8. The `halt-due-to-flakiness` outcome (third amendment).

This is a lot for one ADR. The high-level-advisor considered four shapes:

| Shape | Pros | Cons |
|---|---|---|
| Keep ADR-058 as one document with three amendments. | Preserves history. Single place to read. Cross-references are local. | Length is now ~400 lines and growing. New readers must wade through invalidation history before reaching the active methodology. |
| Split into ADR-058 (methodology) + ADR-058a (worked example, security agent v2 halt + v1 invalidation note). | Methodology stays clean. History stays accessible but separated. | Two-ADR cross-reference pattern. Risk that future readers consult only one. |
| Split into ADR-058 (methodology + symmetry) + a separate `evals/security-spike/HISTORY.md` for the v1 + v2 narrative. | Cleanest methodology document. Spike artifacts retain their own history file. | The HISTORY file is not an ADR and may not get the same review attention. |
| Defer the split decision to after v3 produces a non-halted verdict. | Avoids splitting on a methodology still in motion. The split itself can be informed by what v3 reveals. | Short-term length cost. |

**High-level-advisor's recommendation**: option 4. Defer the split. The methodology is still maturing; a split now would need to be re-shaped after v3. The current document length is a manageable cost; the cost of a premature split is higher.

The high-level-advisor accepts the architect's `proposed` status decision.

## Round 2: Disagreements and Resolution

**Disagreement 1**: Critic raised whether `halt-due-to-flakiness` is a soft escape from `scrap`. Resolution: the operational consequence text explicitly forbids graduation to CI without resolving the variance. The fourth outcome is documented as a halt, not a pass.

**Disagreement 2**: Independent-thinker's vocabulary-recognition reading vs the analyst's content-specialization reading of the +43pp gain. Resolution: the analysis converges on content-specialization (CWE vocabulary in the agent's system prompt produces wins on F004 and F006 where the agent identifies CWE patterns the baseline misses). The vocabulary-recognition reading is rejected on the grounds that the suffix is shared between variants and the agent's system prompt does not contain the suffix's vocabulary.

**Disagreement 3**: High-level-advisor's split recommendation vs architect's keep-as-one recommendation. Resolution: defer the split until v3 produces a clean verdict (or a second halt). Both reviewers agree on this path.

**Disagreement 4**: Analyst's caveat that the non-flaky subset should not be the headline number. Resolution: the worked example reports the all-fixture delta (+38.1pp) as headline; the non-flaky subset (+42.9pp) is supporting context; both numbers are presented with the AC-10 halt context.

## Round 3: Consensus

All six reviewers accept the third amendment with the architect's edit set:

1. v1 invalidation subsection added prominently with citation to `.agents/critique/SPIKE-1854-methodology-diagnosis.md` and verbatim v1 numbers preserved as record-of-rigging.
2. Experimental Design Symmetry subsection added with MUST language; OUTPUT_SHAPE_SUFFIX named as the canonical implementation; the six symmetry checks (model, temperature, fixture input, retry policy, scoring engine, output-shape contract) listed.
3. Worked example replaced with v2 numbers from `report.json`: 78.6% / 40.5% / +38.1pp; non-flaky 100.0% / 57.1% / +42.9pp; cost $0.89; wall ~10 min; verdict `halt-due-to-flakiness`; variance pattern documented.
4. Decision criteria table extended with `halt-due-to-flakiness` as a fourth outcome; operational consequence requires variance investigation before next attempt.
5. Cadence trigger updated: next trigger is variance investigation + corpus expansion, not the quarterly fallback.
6. "What this methodology measures" extended with a third paragraph on the symmetry requirement; v1 cited as the canonical "what NOT to do".
7. v1 archive at `evals/_archive/security-spike-20260503T165136Z-84f918a9/` cross-referenced as preserved evidence.
8. Status remains `proposed`.
9. Second-amendment scope clarification (specialization vs form-factor) preserved unchanged.
10. ADR-058 keeps its current shape (no split); reconsider after v3.

## Outcome

**Status**: APPROVED, applied to `.agents/architecture/ADR-058-agent-eval-discipline.md`.

**Follow-on actions tracked outside this debate log**:

1. Variance investigation: control test `same fixture × same variant × N=10 runs` to quantify temperature=0 non-determinism on long context. (New issue.)
2. Corpus expansion to N≥30 to make the AC-10 halt threshold more informative in absolute terms. (New issue.)
3. Re-evaluate borderline fixtures (F001, F002) for ambiguous expected-verdict design. (New issue.)
4. Reconsider ADR-058 split after v3 produces a clean (non-halted) verdict.

## References

- `.agents/architecture/ADR-058-agent-eval-discipline.md` (post-third-amendment)
- `.agents/critique/ADR-058-debate-log.md` (original ratification)
- `.agents/critique/ADR-058-amendment-debate-log.md` (second amendment, pre-diagnosis)
- `.agents/critique/SPIKE-1854-methodology-diagnosis.md` (four-agent diagnosis)
- `evals/security-spike/reports/20260503T182553Z-eaa08f8d/report.json` (v2 authoritative numbers)
- `evals/security-spike/reports/20260503T182553Z-eaa08f8d/REPORT.md` (v2 markdown narrative)
- `evals/_archive/security-spike-20260503T165136Z-84f918a9/` (v1 archive, evidence of rigged comparison)
- Commit `61f1b6b8` (methodology fix: shared output-shape suffix in `_build_prompt`)
- Commit `5f8fd96f` (v2 re-run, RUN_ID `20260503T182553Z-eaa08f8d`)
- Commit `f0bfec3a` (v1 regex fix; correct under the rigged contract; superseded by symmetry fix)
- Commit `8f1e5342` (v1 rescore commit; superseded)
- Issue #1854 (source spike issue)
- Issue #1875 (form-factor methodology follow-on tracker; unaffected by this amendment)
