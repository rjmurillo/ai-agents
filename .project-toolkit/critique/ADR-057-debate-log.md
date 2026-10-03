# ADR-057 Debate Log: Prompt Behavioral Evaluation Methodology

## Review Date: 2026-04-19

## Phase 1: Independent Reviews

### Architect
- **Verdict**: Accept (with 2 P1 reservations)
- **P1**: Missing vendor lock-in assessment section
- **P1**: Confirmation relies on PR description honor system
- **P2**: Template numbering deviation (numbered vs bulleted decision drivers)
- **P2**: Extra sections not in MADR 4.0

### Critic
- **Verdict**: Needs Revision
- **P1**: Acceptance gate has no enforcement path
- **P1**: Structural/behavioral boundary is ambiguous at edges
- **P2**: Minimum scenario count undefined
- **P2**: Model version tracking absent
- **P2**: Runner implementation fully unspecified

### Independent Thinker
- **Verdict**: Disagree-and-Commit
- **P0**: 80/20 claim (scenario vs golden corpus value) is unsubstantiated
- **P1**: Flakiness protocol gap (no retry counts or confidence thresholds)
- **P1**: Missing cost model (no token/dollar estimates)

### Security
- **Verdict**: Disagree-and-Commit
- **P0**: Probabilistic gates create false confidence for security-critical prompts
- **P1**: Prompt injection risk in eval scenarios (no input sanitization guidance)
- **P1**: API key exposure risk (no env-var mandate)
- **P2**: Inactive security prompts unmonitored for model drift

### Analyst
- **Verdict**: Disagree-and-Commit
- **P1**: No cost estimate (reversal trigger unactionable)
- **P1**: "Active iteration" undefined (monthly cadence unenforceable)
- **P1**: No scenario adequacy guidance (thin coverage risk)
- **P2**: No analysis of whether prompt discipline alone could defer eval infrastructure

### Advisor
- **Verdict**: Accept
- **P1**: Operational scheduling details (monthly runs, model bump triggers) belong in methodology doc, not ADR
- **P2**: Intentional trade-off clause missing for pass-to-fail flips

## Phase 2: Consolidation

### Consensus Points
- Core decision is sound (6/6 agree scenario-based evals are the right approach)
- Issue #1686 provides sufficient motivation (6/6 agree)
- ADR is warranted vs methodology doc alone (6/6 agree)
- Additive to ADR-023, no conflicts (6/6 agree)

## Phase 3: Resolution

### Conflict Points (Resolved in Phase 3)
- P0: 80/20 claim removed, replaced with honest uncertainty
- P0: Security-critical prompt tier added with 5-run, 100% pass requirement
- P1: Enforcement path clarified (code review now, PR template next, CI future)
- P1: Tiebreaker rule added (ambiguous changes default to behavioral eval)
- P1: Flakiness protocol added (3 runs, 2/3 pass for non-security)
- P1: Cost estimate added (~20-50K tokens per cycle, $50/month ceiling trigger)
- P1: "Active iteration" defined (modified in last 30 days or open linked issues)
- P1: Scenario adequacy minimum defined (1 per decision branch + 1 regression)
- P2: API key env-var mandate added
- P2: Model provenance tracking added
- P2: Intentional trade-off clause added

## Phase 4: Final Verdicts (Post-Resolution)

| Agent | Original Verdict | Post-Fix Assessment |
|-------|-----------------|---------------------|
| Architect | Accept | Accept (P1s addressed) |
| Critic | Needs Revision | Accept (enforcement path and boundary rule added) |
| Independent Thinker | D&C | Accept (80/20 removed, flakiness protocol added) |
| Security | D&C | Accept (security tier added, API key mandate added) |
| Analyst | D&C | Accept (cost model, adequacy, active iteration defined) |
| Advisor | Accept | Accept (no changes needed) |

**Consensus: 6/6 Accept**

## Recommendations to Orchestrator

1. Update PR template to include eval score section (tracked as follow-up)
2. Update `.project-toolkit/testing/prompt-eval-methodology.md` to back-reference ADR-057
3. Consider moving operational scheduling details to methodology doc in future revision

---

## Amendment 2026-09-30 (Issue #5601): verdict-only scoring and a stable-base comparison

ADR-057 is amended in PR #6079. Owner decision D12 approved the amendment. The change was written against `scripts/eval/eval-prompt-change.py`.

### Panel

Two of six agents ran: architect and critic. The session cap is three subagents with two concurrent, and the change describes existing code rather than adding enforcement. The other four agents did not review. This is a reduced panel, recorded as such.

### Round 1 findings and resolution

| # | Agent | Priority | Finding | Resolution |
|---|-------|----------|---------|------------|
| 1 | architect | P1 | Criterion 4 says "passes only some runs", but the code treats only 2 of 3 as unstable. A base at 1 of 3 stays in the scores. | Fixed. Criterion 4 and the Decision paragraph now state the 2-of-3 rule and the 1-of-3 case. |
| 2 | architect | P1 | The Confirmation table has no row for `has_stable_baseline`. | Fixed. Row added, and the pass-to-fail row now says stable-base scenarios. |
| 3 | architect | P2 | Frontmatter date stale. | Fixed to 2026-09-30. |
| 4 | architect | P2 | Scenario Adequacy omits that an unstable scenario gives no protection. | Fixed. SHOULD added for one scenario that passes every base run. |
| 5 | architect | P2 | The `reason_mismatch_scenarios` sentence is not scoped. | Fixed. States after side, passing runs. |
| 6 | architect | P2 | Security tier silent on criterion 4. | Fixed in the Confirmation row: it applies at 5 runs. |
| 7 | architect | P2 | The 2026-06-01 relaxation text is historical. | Fixed. Pointer to this amendment added. |
| 8 | critic | P1 | One stable scenario of N satisfies criterion 4. | Deferred, documented as an accepted limit. A minimum count or fraction needs a measured false-block rate from live runs. |
| 9 | critic | P1 | Stable base needs 3 of 3, but the after side passes at 2 of 3, so 3 to 2 is not a regression. | Deferred, documented as an accepted limit. A stricter after-side threshold needs live data. |
| 10 | critic | P1 | Two-valued scenarios (D12) can be stable or pass by chance once the reason check is gone. | Deferred, documented as an accepted limit. A chance correction needs live data. |
| 11 | critic | P2 | Residual risk understated. | Fixed. The Decision's trade-off paragraph names all three limits. |
| 12 | critic | P2 | Criterion 4 names no numbers. | Deferred with findings 8 to 10. |
| 13 | critic | P2 | A base with not-scored runs can be "stable" on one scored run. | Not changed here. Existing behavior of `insufficient_scored_before`, outside this amendment. |

No P0 findings. Deferred items 8, 9, 10, and 12 are recorded in the ADR text. No issue was filed because filing needs owner authorization.

### Votes

| Agent | Vote |
|-------|------|
| architect | Disagree and Commit |
| critic | Disagree and Commit |

Dissent: the gate can pass with most scenarios excluded, and the 3-to-2 drop is unguarded. The ADR now states both as accepted limits.

**Outcome: 2/2 reviewing agents Disagree and Commit. Strategic checklist: Chesterton's Fence PASS (original reason-contains purpose and the defect it caused are recorded), Path Dependence PASS (rollback is a revert), Core vs Context N/A, Second-System N/A.**

---

## Amendment 2026-10-02 (Issue #5601): full six-agent panel

Review thread PRRT_kwDOQoWRls6nxewN on PR #6079 asked for the full panel. The change touches executable enforcement, so AGENTS.md requires all six agents. The owner approved the full panel (decision D2). The owner also approved adding the stable-scenario floor (decision D3).

### Panel

All six agents ran. Analyst, security, independent-thinker, and high-level-advisor reviewed the whole amendment. Architect and critic reviewed the delta since their 2026-09-30 votes.

### Round 1 findings and resolution

| # | Agent | Priority | Finding | Resolution |
|---|-------|----------|---------|------------|
| 14 | analyst | P2 | A base that fails every scenario still satisfies the baseline. | Fixed. The ADR states it as intended: a failing base cannot regress. |
| 15 | analyst | P2 | Base stability is judged on scored runs, and the run floor bound only the after side. | Fixed. A base scored below the minimum now counts as unstable. |
| 16 | analyst | P2 | Deferred limits had no revisit trigger. | Fixed. Each deferred limit names a trigger. |
| 17 | analyst | P2 | The `--runs` row omitted the non-security minimum of 3. | Fixed. |
| 18 | security | P1 | Exclusion of unstable base scenarios had no cap. One stable scenario let a 2/3 base, 0/3 after regression escape. | Fixed in `1aa33a691`. The gate needs `max(1, ceil(total/2))` stable scenarios, else FAIL as inconclusive. |
| 19 | security | P1 | A provider outage exits 0, so the gate passes when it cannot run. | Deferred. It predates #5601. The ADR records it as fail-open. It must be fixed before this eval becomes a required check. No issue was filed, because filing needs owner authorization. |
| 20 | security | P2 | Excluded security-tier scenarios were not reported apart. | Fixed. They are listed in `base_unstable_security_scenarios`. |
| 21 | security | P2 | The ADR did not say whether the security tier changed. | Fixed. The ADR states it is unchanged. |
| 22 | independent-thinker | P1 | The stable set comes from one noisy 3-run base sample, so gate membership varies between reruns. | Deferred. The floor bounds the damage. Revisit after 10 live gate runs, an exclusion rate above 25%, or a scenario that flips between stable and unstable. A pooled paired test is the long-term design. |
| 23 | independent-thinker | P1 | No minimum stable fraction. | Same as finding 18. Fixed. |
| 24 | independent-thinker | P2 | The ceiling threshold is not monotone in scored runs. | Fixed. The ADR lists required passes 1, 2, 2, 3, 4, 4 for 1 to 6 scored runs. |
| 25 | independent-thinker | P2 | Verdict-only scoring trades false blocks for false passes. | Fixed. The ADR records the trade-off. |
| 26 | architect | P2 | The SHOULD at line 147 still described the one-scenario rule. | Fixed in `bbd22c03f`. |
| 27 | architect | P2 | The outage trigger has no tracking issue. | Not changed. Filing an issue needs owner authorization. |
| 28 | architect | P2 | Frontmatter date was stale. | Fixed to 2026-10-02. |
| 29 | critic | P1 | The floor read `scored_scenario_count` while the gate counted exclusions on its own. A comparison without the count skipped the floor. | Fixed in `bbd22c03f`. The floor uses the gate's own exclusion set. A supplied count can only lower it. |
| 30 | critic | P1 | Tests built inputs through a helper that skipped the base-minimum rule. | Fixed in `bbd22c03f`. The helper mirrors `run_comparison`. New tests cover omitted counts, the security floor end to end, and a nonzero exit on an inconclusive FAIL. |
| 31 | critic | P2 | A failing base scored below the minimum is now excluded, but nothing pinned it. | Fixed. A test pins it, and the docstring says so. |

No P0 findings. Findings 8, 9, 10, and 12 from 2026-09-30 stay deferred, under the trigger named in finding 22.

### Votes

| Agent | Vote |
|-------|------|
| analyst | Accept |
| security | Disagree and Commit |
| independent-thinker | Disagree and Commit |
| high-level-advisor | Disagree and Commit, to Accept once the floor landed |
| architect | Accept |
| critic | Disagree and Commit |

Dissent: the provider outage stays fail-open, and the stable set still depends on base sampling noise. Both are recorded as accepted limits with triggers. The critic voted on `1aa33a691`, and its two P1 findings were fixed after that vote in `bbd22c03f`.

**Outcome: 6/6 Accept or Disagree and Commit. Strategic checklist: Chesterton's Fence PASS, Path Dependence PASS (rollback is a revert), Core vs Context N/A, Second-System N/A.**

---

## Correction 2026-10-03 (Issue #5601): criterion 4 fallback wording

A review thread on PR #6079 found that criterion 4 still said a comparison without `scored_scenario_count` is treated as having every scenario stable. The code derives the stable count from the gate's own exclusion set (finding 29). The sentence now says so. This edit changes wording only, so a reduced panel of architect and critic reviewed it.

| # | Agent | Priority | Finding | Resolution |
|---|-------|----------|---------|------------|
| 32 | architect | none | The sentence matches `eval-prompt-change.py:731-738`. | None. |
| 33 | critic | P2 | The two supplied-count tests assert only the FAIL verdict, not the inconclusive reason. | Not changed. Recorded for a later test pass. |
| 34 | critic | P2 | `test_gate_without_scored_count_assumes_a_baseline` keeps the old wording in its name. | Not changed. Recorded for a later test pass. |

### Votes

| Agent | Vote |
|-------|------|
| architect | Accept |
| critic | Accept |
