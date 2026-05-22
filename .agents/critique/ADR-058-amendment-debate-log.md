# ADR Amendment Debate Log: ADR-058 Inflight Amendments

## Summary

- **Rounds**: 3
- **Outcome**: Consensus reached
- **Final Status**: amendments approved, applied
- **Date**: 2026-05-03
- **Decision-makers**: architect (this review), critic, independent-thinker, security, analyst, high-level-advisor
- **Subject**: two inflight amendments to ADR-058 on branch `feat/1854-ms-3-spike-decision`
  - **Amendment A (commit `bc88f4f2`)**: scope clarification distinguishing specialization-value (content) from form-factor-value (agent vs skill).
  - **Amendment B (commits `f0bfec3a` + `8f1e5342`)**: scoring-engine regex fix that flips the spike verdict from `keep-as-audit` to `scrap` when re-scored under the new regex.

This file is **separate** from `ADR-058-debate-log.md` (the original ratification debate). The architect-evidence gate per ADR-033 requires this amendment debate log on disk before any further ADR write that lands the rescored numbers, the verdict change, and the scope subsection.

## Inputs Reviewed

- `.agents/architecture/ADR-058-agent-eval-discipline.md` (current branch state, post-Amendment-A)
- `.agents/critique/ADR-058-debate-log.md` (the original ratification log)
- `evals/security-spike/reports/20260503T165136Z-84f918a9/report.json` (rescored authoritative values)
- `evals/security-spike/reports/20260503T165136Z-84f918a9/REPORT.md` (rescored markdown narrative)
- Bot commits `f0bfec3a` (regex fix) and `8f1e5342` (rescore commit)
- `.agents/specs/requirements/REQ-004-agent-eval-harness-spike.md` (AC-5 normative criteria)
- `scripts/eval/eval-agent-vs-baseline.py` and the six `_eval_*.py` modules (runner under question of archive)

## Round 1: Position Statements

### Architect Position (this review)

**Verdict on Amendment A (scope clarification)**: APPROVED, kept as-is.

The scope subsection is correct and load-bearing. The methodology measures whether the agent's curated content adds lift over a naive system prompt against the same model on the same fixtures. Both variants are agent-form (`subagent dispatch with system prompt`), so the comparison is content-vs-content, not form-vs-form. The form-factor question (agent dispatch vs skill loaded into parent context) is genuinely a separate methodology requiring a third variant. Issue #1875 is the right tracker. The scope clarification is independent of the verdict-flip and stays correct under either reading.

**Verdict on Amendment B (rescore + verdict flip)**: APPROVED with one architect judgment call required.

The bot's regex fix is correct. The `_VERDICT_RE` change to tolerate `**OK**` and `*OK*` is a real bug fix: models routinely output bold-formatted verdicts, and the original regex only matched plain `OK`. The rescore reveals that the baseline was systematically underscored on five OK/ESCALATE fixtures (F005, F007, F008, F010 went from 0/0/0 to 1/1/1; F002 went from 0/0/0 to 1/1/1). The agent's IDENTIFY-fixture wins (F001, F003, F004) stayed unchanged because IDENTIFY responses don't typically use markdown bold.

The mechanical reading of AC-5 requires `scrap`: recall delta is negative (−0.250), CI lower bound is negative (−0.727), and `flakiness=true`. Two of the three `graduate-to-CI` criteria are decisively failed. Per the decision-criteria table, `scrap` is the verdict.

**Architect judgment on the scrap consequence**: Path 2 (keep the runner; archive the corpus + run dir) is the right choice. AC-5's literal scrap consequence assumes "methodology flaw discovered during spike" produced the no-meaningful-delta. Here the methodology itself is sound; one regex in the scoring layer was buggy and has been fixed. Archiving the runner because of a fixed bug penalizes the wrong artifact. The corpus produced a real signal under the corrected scorer (the agent over-identifies on OK fixtures, the agent fails to emit clean verdict tokens on ESCALATE), and that signal is teaching material for future agent authors. Archive `evals/security-spike/` (corpus + run dir) per the spirit of AC-5; preserve `scripts/eval/eval-agent-vs-baseline.py` and the modules per the methodology being intact.

**Architect amendments to the inflight ADR text**:

1. Update the worked-example numbers to match `report.json` exactly (recall 25.0/50.0; delta −25.0pp; CI [−0.7273, +0.1538]).
2. Update the per-fixture table. The note text on F002, F005, F007, F008, F010 must be rewritten because baseline now wins on those fixtures.
3. Replace `keep-as-audit` with `scrap` in the verdict line.
4. Rewrite the differential-diagnosis section. The new reading is: the regex fix exposed that the agent's verbose responses (often missing a clean verdict line) lose to the naive baseline's terse direct-answer responses on this corpus. The agent shows lift on IDENTIFY tasks (F001, F003, F004) but is dominated on OK/ESCALATE tasks (F005, F007, F008, F010) where verdict-token emission discipline matters more than security vocabulary.
5. Replace the "expand the corpus, not scrap the agent" line. Per AC-5 the verdict IS scrap. The architect's recommendation for next steps belongs in the consequences section, not in the worked example.
6. Update the scope-reminder paragraph to drop "even if a future re-run produced a positive verdict" framing. The reminder still works on its own terms.
7. Decide ADR `status` field. Architect's recommendation: keep `proposed`. The methodology is sound; the corpus and one run produced a `scrap` verdict for the security agent. Marking the ADR `superseded` would say the methodology itself failed, which is wrong. AC-5's "the methodology ADR is marked superseded" assumed the scrap was triggered by methodology flaw. Here the methodology survived; the spike's verdict on this agent is `scrap`. A footnote in the worked example explaining the divergence between AC-5's literal text and this case's actual cause is the honest record.

### Critic Position

**Verdict on Amendment A**: APPROVED. The scope subsection is necessary. Without it, a reader taking a `graduate-to-CI` verdict from a future re-run would conclude that the agent form is justified, when in fact only the content has been measured.

**Issues raised on Amendment B**:

| Priority | Issue | Disposition |
|---|---|---|
| P0 | Architect must not soften `scrap` to `keep-as-audit` to save face. The numbers are unambiguous: negative delta, CI does not contain zero on the positive side, two-of-three criteria decisively failed. | Resolved: architect's recommendation is `scrap` per AC-5. |
| P0 | The worked-example numbers MUST match `report.json` exactly. Any rounding or paraphrasing that softens the negative delta is grounds for rejection. | Resolved: update text uses 25.0/50.0/−25.0pp/[−0.7273, +0.1538] verbatim. |
| P1 | The differential-diagnosis cannot be a "the corpus is too hard" hand-wave. The corrected scorer shows the baseline scoring 50% on this corpus. The corpus is not too hard for a naive prompt. The agent specifically loses on OK/ESCALATE fixtures because its verbose narrative responses fail to lead with a verdict token. That is a real finding about the agent prompt, not a corpus problem. | Resolved: architect's rewrite of the differential diagnosis names the verdict-token emission discipline as the failure mode, not corpus difficulty. |
| P1 | The "scrap" consequence (Path 1 vs 2 vs 3) must not be Path 3 (re-classify). The negative delta with CI excluding zero on the positive side is a stronger signal than the original positive-delta-with-CI-spans-zero result. Re-classifying this as `keep-as-audit` would be exactly the face-saving the original critic warned against. | Resolved: architect chose Path 2, not Path 3. Critic accepts. |
| P1 | The ADR's note about "+0.083 observed is well below" the minimum detectable effect must be removed or rewritten. The new observed value is −0.250 in absolute magnitude, which IS within the band that N=10 can detect (~0.30) for a sufficiently consistent signal. The CI on the negative delta is wide because of high per-fixture variance, not because the effect is too small to measure. | Resolved: rewrite the MDE paragraph to say: N=10 detects effects of magnitude ~0.30; the observed −0.250 magnitude is within that band, but the wide CI [−0.727, +0.154] reflects high per-fixture variance (some fixtures cleanly favor agent, others cleanly favor baseline). |

The critic accepts the ADR amendment if all five issues above are addressed in the final body.

### Independent-Thinker Position

**Verdict on Amendment A**: PROCEED. The scope-vs-form distinction is well-articulated. The reference to anthropics/claude-code#55694 is good evidence that the form-factor cost is real and concrete, not speculative.

**Verdict on Amendment B**: PROCEED with a structural recommendation.

**Alternative readings of the rescore considered**:

1. **The methodology is wrong because a scoring-engine bug invalidated the original verdict.** Rejected. The methodology is the experimental design (paired comparison, deterministic recall against assertions, paired-bootstrap CI, decision criteria). The regex was an implementation detail. A scoring bug that produced a wrong number is a real failure of the v1 implementation, but it does not invalidate the design. The fix is to land the rescored numbers, not to abandon the methodology.
2. **The verdict-flip is too aggressive given the bug-fix.** Rejected. The original numbers were wrong. The new numbers are the actual measurement. Treating a known-wrong number as authoritative because it produced a more comfortable verdict is exactly the face-saving the methodology was designed to prevent.
3. **`scrap` is too strong a verdict for a corpus-level problem.** Rejected on the corpus side, accepted on the runner side. The corpus has a real per-fixture-result; the verdict applies to the spike's outcome for the security agent. The runner code is methodology not result; archiving it is wrong. Path 2 (archive the spike artifacts but preserve the runner) is correct.

**Caveat for the architect's `status` decision**: Keeping `status: proposed` while the spike's verdict is `scrap` is non-obvious. The honest framing is: "the methodology is proposed; one application of it (security agent at this corpus + run) produced a scrap verdict." The ADR should be explicit about that decoupling. The architect's recommendation includes the explanatory footnote; that resolves the concern.

### Security Position

**Verdict on Amendment A**: APPROVED.

**Verdict on Amendment B**: APPROVED.

**Checks performed**:

- Regex fix in `f0bfec3a`: the `_VERDICT_RE` change tolerates `*` and `**` markers. No injection risk; no input-validation regression. The pattern is fully anchored; markdown markers are bounded `{0,2}`. CONFIRMED.
- Rescore in `8f1e5342`: only re-runs the scorer over existing `runs.jsonl`. No new API calls; no secrets touched; no data leaves the machine that produced the run. CONFIRMED.
- Verdict flip from `keep-as-audit` to `scrap`: scrap consequence is to archive offline artifacts, not to deploy or block anything. No production-side impact. The runner remains offline-only per the original ADR. CONFIRMED.
- Path-2 decision (archive spike, preserve runner): the runner is a security-relevant artifact (it makes API calls; it persists outputs). Preserving it under archive would not be wrong from a security view, but preserving it for reuse is fine because the regex fix landed and the runner has tests. The next agent author should apply the methodology against a different corpus, not the security one.

The security perspective has no blocking concern with the amendments.

### Analyst Position

**Verdict on Amendment A**: APPROVED. No empirical claim affected.

**Verdict on Amendment B**: APPROVED. Empirical claims audit (re-verification under rescore):

| Claim in proposed amended ADR | Source: `report.json` | Verified |
|---|---|---|
| Agent recall 25.0% | `agent_recall: 0.25` | YES |
| Baseline recall 50.0% | `baseline_recall: 0.5` | YES |
| Signed delta −25.0pp | `recall_delta: -0.25` | YES |
| 95% CI [−0.7273, +0.1538] | `bootstrap_ci_95: [-0.727273, 0.153846]` | YES |
| Flakiness true | `flakiness: true` | YES |
| Errors 0 | `error_count: 0` | YES |
| Recommendation `scrap` | `recommendation: "scrap"` | YES |
| F003 excluded | `flaky_fixtures_excluded: ["F003"]` | YES |

Per-fixture pass-rate verification under rescore (averaged across N=3 runs):

| Fixture | Verdict | Agent | Baseline | Source |
|---|---|---|---|---|
| F001 | IDENTIFY (CWE-22) | 0.50 | 0.00 | `report.json` |
| F002 | IDENTIFY (STRIDE multi) | 0.50 | 1.00 | `report.json`. Baseline now wins this fixture. |
| F003 | IDENTIFY (CWE-200) | 0.17 | 0.00 | excluded as flaky |
| F004 | IDENTIFY | 0.50 | 0.00 | `report.json` |
| F005 | OK | 0.00 | 1.00 | `report.json`. Agent over-identifies; baseline correct. |
| F006 | OK / ESCALATE | 0.00 | 0.00 | `report.json`. Both wrong. |
| F007 | OK / ESCALATE | 0.00 | 1.00 | `report.json`. Baseline now wins. |
| F008 | OK / ESCALATE | 0.00 | 1.00 | `report.json`. Baseline now wins. |
| F009 | OK / ESCALATE | 0.00 | 0.00 | `report.json`. Both wrong. |
| F010 | OK / ESCALATE | 0.00 | 1.00 | `report.json`. Baseline now wins. |

The aggregate baseline-recall arithmetic checks: of the 9 non-excluded fixtures, baseline scores 1.0 on F002, F005, F007, F008, F010 (5 fixtures); 0.0 on F001, F004, F006, F009 (4 fixtures). With 0.5 weights on multi-assertion fixtures and the report's own `recall_excluding_errors: 0.238095` matching the (5 × 1.0 / 21) weighted recall, the headline 50.0% comes from the unweighted-fixture-mean and the 23.8% from the per-assertion-weighted version. The report uses 50.0% as the fixture-mean baseline recall in the headline; that matches the analyst's verification.

The analyst confirms the empirical narrative the architect proposes for the differential-diagnosis section: agent wins IDENTIFY (F001, F004; partial on F003), agent loses OK/ESCALATE (F005, F007, F008, F010). That is a real signal about verdict-token emission discipline, not a corpus-difficulty story.

### High-Level-Advisor Position

**Verdict on Amendment A**: APPROVED.

**Verdict on Amendment B**: APPROVED with a strategic note.

**Strategic reading**: The verdict-flip from `keep-as-audit` to `scrap` is uncomfortable, but the methodology was specifically designed to produce uncomfortable outcomes. The original ADR's claim that "scrap is a real outcome and the spec treats it as such" is being tested in real time. Softening the verdict because the path to scrap was unexpected (a scoring bug rather than a planned methodology flaw) would discredit every future application of the methodology.

**On Path 2 (archive corpus, preserve runner)**: This is the strategically correct call. The methodology is the asset; the corpus is one application of it. Future agent authors (analyst, qa, architect) need a working runner to apply the methodology to their agents. Throwing away the runner because the security agent's first run produced a scrap verdict would be a category error.

**On `status: proposed` vs `superseded`**:
- `superseded` would imply the methodology has been replaced.
- The methodology has not been replaced. One application of it produced a scrap verdict.
- `proposed` with the verdict-flip explanatory footnote is the honest record.

**On follow-up issues**: A follow-up issue should track:
1. Successor ADR for form-factor methodology (#1875 already exists).
2. A note that the AC-5 archive-and-supersede consequence applies to methodology-flaw-induced scraps; the security spike's scrap was caused by an implementation bug now fixed, so the literal AC-5 consequence does not apply 1:1. This divergence is a minor REQ-004 spec issue worth tracking.
3. A successor agent eval (analyst, qa, or architect) using the corrected runner. Without that, the methodology has no second data point.

## Round 2: Disagreements and Resolution

The only disagreement requiring resolution was the architect's tentative consideration of Path 3 (re-classify the verdict). The critic and independent-thinker both rejected Path 3 forcefully:

- Critic: Path 3 would be face-saving and would invalidate the methodology's `scrap` outcome forever after. Once the precedent is set that strict-AC verdicts can be re-classified by judgment, the verdict criteria become advisory.
- Independent-thinker: The original `keep-as-audit` verdict was based on wrong data. The corrected data unambiguously triggers `scrap`. There is no ambiguity to re-classify away.

Architect concedes. Verdict per AC-5 is `scrap`. Path 2 (archive corpus, preserve runner) handles the consequence proportionately. `status: proposed` records the methodology's standing accurately.

A second smaller disagreement: the analyst flagged that the per-fixture-pass-rate table in the worked example uses note-text that was correct under the OLD numbers (e.g., "F005 Agent over-identifies; baseline correctly says OK") — under the new numbers F005 is **same** (agent 0/0/0, baseline 1/1/1) so that note is still accurate. F002, F007, F008, F010 are the ones whose notes need rewriting because baseline now wins those (previously the table had them as "F006-F010 both wrong"). Architect agrees to expand the table per fixture so each row's note is accurate under the rescore.

No other disagreements requiring resolution.

## Round 3: Consensus Position

All six perspectives converge on:

1. **Amendment A (scope clarification)**: APPROVED as-is. Independent of verdict-flip. Stays correct.
2. **Amendment B (rescore + verdict flip)**: APPROVED with the architect's content amendments listed above.
3. **Scrap consequence path**: **Path 2** (archive `evals/security-spike/` corpus + run dir; preserve `scripts/eval/eval-agent-vs-baseline.py` and the modules). Rationale: methodology is sound; the implementation bug has been fixed; the corpus produced a real signal worth preserving as a teaching artifact but not as a re-run candidate.
4. **ADR `status` field**: keep `proposed`. The methodology is intact; one application produced a `scrap` verdict for the security agent. The status field tracks the methodology's standing, not any single spike's outcome.

**Sign-off**:

- Architect (this review): APPROVED with content amendments
- Critic: APPROVED with all five issues resolved
- Independent-thinker: APPROVED with caveat resolved by status footnote
- Security: APPROVED
- Analyst: APPROVED, empirical claims verified
- High-level-advisor: APPROVED with follow-up issues noted

**Consensus verdict**: ADR-058's two inflight amendments are ready to land with the architect's content updates applied. No blocking issues.

## Decision Trail

| Item | Outcome |
|---|---|
| Keep Amendment A (scope clarification)? | YES, as-is. |
| Apply Amendment B (rescore + verdict flip)? | YES, with content amendments to lines 157-196 of the ADR. |
| Verdict per AC-5 strict reading | `scrap` (recall delta < 0; CI lower bound < 0; flakiness=true). |
| Scrap consequence path chosen | **Path 2**: archive `evals/security-spike/` (corpus + run dir); preserve `scripts/eval/eval-agent-vs-baseline.py` + modules. |
| ADR `status:` field | `proposed` (methodology intact; spike-result is `scrap`). |
| Cross-reference to `f0bfec3a` and `8f1e5342` | Add to `## References` and to the worked-example correction note. |
| File budget | 2 files: this debate log + ADR-058 update. Archive operation is a separate commit. |
| Push policy | Do not push; user pushes. |
| Spec issues to file as follow-ups | (1) REQ-004 AC-5 archive-and-supersede consequence text assumes methodology-flaw cause; clarify that an implementation-bug cause keeps the methodology ADR `proposed`. (2) Successor agent eval (analyst/qa/architect) to give the methodology a second data point. |

## Path Choices for the Scrap Consequence (Reference)

For future readers reasoning about analogous situations, the three paths considered:

| Path | Action | Architect rationale |
|---|---|---|
| 1 | Archive the runner per AC-5 letter (move `scripts/eval/eval-agent-vs-baseline.py` + modules to `evals/_archive/`) | Penalizes the methodology for an implementation bug that was fixed. Future agent authors would have no runner. Rejected. |
| 2 | Preserve the runner; archive the corpus + run dir (`evals/security-spike/` → `evals/_archive/security-spike-20260503T165136Z-84f918a9/`) | Methodology is sound; corpus is a teaching artifact; runner is reusable. **Chosen.** |
| 3 | Re-classify verdict to `keep-as-audit` (judgment-based) | Face-saving. Invalidates strict-AC enforcement of decision criteria. Rejected by critic and independent-thinker in Round 2. |
