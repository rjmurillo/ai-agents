# ADR Debate Log: ADR-058 Agent Eval Discipline

## Summary

- **Rounds**: 3
- **Outcome**: Consensus reached
- **Final Status**: ratified
- **Date**: 2026-05-03
- **Decision-makers**: architect, user
- **Subject**: ADR-058 Agent Eval Discipline (Agent-vs-Baseline Efficacy)

This log documents the architect-led multi-perspective review of ADR-058 prior to ratification. The ADR codifies the agent-vs-baseline efficacy methodology validated by the issue #1854 spike (run `20260503T165136Z-84f918a9`). The architect-evidence gate per ADR-033 requires this debate log on disk before the ADR write.

## Inputs Reviewed

- `.agents/specs/requirements/REQ-004-agent-eval-harness-spike.md` (AC-6)
- `.agents/specs/design/DESIGN-004-agent-eval-harness-spike.md`
- `.agents/architecture/ADR-057-prompt-behavioral-evaluation.md` (sibling)
- `.agents/architecture/ADR-053-adr-exception-criteria.md` (frontmatter conventions)
- `evals/security-spike/reports/20260503T165136Z-84f918a9/REPORT.md` (worked example numbers)

## Round 1: Position Statements

### Architect Position

**Verdict**: APPROVED with two amendments.

**Methodology soundness**:
- Deterministic-only gating is correct for an agent-vs-baseline question because the dependent variable (recall on tagged CWE/STRIDE assertions) is checkable without LLM judgment. LLM-as-judge would introduce a confounding probabilistic measurement on top of a probabilistic system under test.
- Paired-bootstrap CI at the fixture level is the right inferential framework for N=10 paired observations. Wilcoxon signed-rank would also work; bootstrap is more honest about the small-N regime.
- Per-agent calibration (rejecting a global magic threshold) is correct. A single recall threshold would over-fit to whichever agent set it.
- The deliberately-naive baseline contract is the load-bearing methodological choice. Without it, the comparison degenerates into "agent vs. a baseline that already contains the agent's vocabulary," which trivializes any positive delta.

**AC-6 coverage**: All 14 acceptance criteria from REQ-004 AC-6 are addressable in the prepared content. The architect verified clauses for fixture schema, provenance rules, deterministic-only gated path, baseline pinning, threshold methodology, cadence, ADR-057 cross-reference, scope (deterministic-scorable agents only), held-out definition, deliberately-naive baseline, worked-example threshold calibration, CI cost projection, decision owner / scrap consequences, survivorship bias acknowledgment, and the advice-quality advisory carve-out.

**Distinction from ADR-057**: ADR-057 answers "did this prompt edit regress behavior?" (before/after on the same prompt artifact). ADR-058 answers "does the agent specialization beat a generic prompt on the same model?" (between-subjects efficacy). Different question, different gate, different runner. The two ADRs are complementary, not overlapping. ADR-058 must cite ADR-057 explicitly and label the distinction.

**Architect amendments requested**:

1. The decision criteria table must use the same column structure as the spec (REQ-004 AC-5) so the ADR is grep-able against the spike report. The prepared content already does this.
2. The "scrap" outcome must be treated as a real and respected outcome with operational consequences (archive `evals/security-spike/`, supersede the ADR). The prepared content already does this.

### Critic Position

**Verdict**: NEEDS REFINEMENT (resolvable in this PR).

**Issues raised**:

| Priority | Issue | Disposition |
|---|---|---|
| P1 | Over-claiming risk on N=10. Reader could mistake the +8.3pp number for a generalizable agent benefit. | Resolved: the ADR worked-example section labels CI as spanning zero, names "keep-as-audit" as the verdict, and quotes the minimum detectable effect size (~0.30 with N=10). |
| P1 | Survivorship bias must be present in the ADR body, not buried in a footnote. The security agent was chosen because it had the crispest deterministic signal; this constrains generalization. | Resolved: a dedicated "Survivorship bias" subsection appears before the worked example. |
| P2 | Cost projection numbers must be honest about the heuristic. The $1.20 figure used a 4-chars-per-token estimate, not measured token usage. | Resolved: ADR cost section states the heuristic explicitly and notes that production projections must use measured `usage` from the API. |
| P2 | "Scrap" must not be face-saving. The criteria must clearly admit that no-delta is a real outcome. | Resolved: scrap operational consequence (archive + supersede) is explicit. |
| P1 | The ADR must NOT define "held-out" as "absent from training data." That is an unverifiable claim. | Resolved: the ADR uses the verbatim definition from REQ-004 AC-6 ("not used in any prior agent eval; does NOT mean absent from training data"). |

The critic accepts the ADR if all five amendments are present in the final body. They are.

### Independent-Thinker Position

**Verdict**: PROCEED with caveats logged.

**Alternative framings considered and rejected** (the ADR must record both the rejection and the rationale):

1. **LLM-as-judge as the gated signal**. Rejected because it confounds two probabilistic systems and makes drift in the judge prompt indistinguishable from drift in the agent under test. The ADR keeps LLM-as-judge as an *advisory* sidecar only. This is defensible.
2. **Golden corpus / large-N evaluation**. Rejected as premature for a v1 spike. ADR-057 already rejected golden-corpus for the same scale reasons. Consistency with the sibling ADR is good.
3. **Single global delta threshold (e.g., "agent must beat baseline by 10pp")**. Rejected because it over-fits to the first agent measured. Per-agent calibration is the right call.
4. **Skip baseline; just score agent recall against an absolute target**. Rejected because absolute targets are unfalsifiable when corpus difficulty is unknown. Paired comparison against a deliberately-naive baseline isolates the prompt-specialization effect.

**Caveat logged**: The deliberately-naive baseline must be SHA-pinned and version-controlled. If the baseline drifts (someone edits it to "improve" it), every prior delta becomes incomparable. The ADR must cite the baseline file path and require a version bump procedure on edit. The prepared content addresses this.

### Security Position

**Verdict**: APPROVED.

**Checks performed**:

- API key handling: ADR delegates to `_anthropic_api.load_api_key()`, which reads from environment variables. No secrets in fixtures, no secrets in scenario files, no secrets in run records. CONFIRMED.
- Fixture provenance: ADR explicitly rejects real third-party secrets at ingest (AC-4). CONFIRMED.
- Cost-disclosure honesty: ADR labels the cost figure as a heuristic with rate-as-of-date, not a contract. CONFIRMED.
- Scope of impact: methodology is offline-only; not a CI gate; cannot block merges; cannot leak data. CONFIRMED.
- The ADR must NOT recommend automatic CI integration without a follow-up security review of the runner's API surface. The prepared content correctly limits "graduate-to-CI" to a follow-up issue, not an automatic action.

### Analyst Position

**Verdict**: APPROVED.

**Empirical claims audit** (against the spike report):

| Claim in ADR | Source | Verified |
|---|---|---|
| Agent recall 25.0% | REPORT.md line 12 | YES |
| Baseline recall 16.7% | REPORT.md line 13 | YES |
| Signed delta +8.3pp | REPORT.md line 14 (+0.0833) | YES |
| 95% CI [-0.20, +0.31] | REPORT.md line 15 ([-0.2000, +0.3077]) | YES (rounded honestly) |
| Flakiness true | REPORT.md line 19 | YES |
| Errors 0 | REPORT.md line 18 | YES |
| Cost ~$1.20 | REPORT.md line 50 ($1.2023, heuristic) | YES (with disclaimer) |
| Wall clock ~11 min | REPORT.md line 51 (663.1s) | YES |
| F003 excluded | REPORT.md line 59 | YES |
| F005 over-identifies (agent 0.00, baseline 1.00) | REPORT.md line 31 | YES |

The empirical claims in the ADR are 1:1 with the spike report. Numbers are not invented and not rounded in a flattering direction.

### High-Level-Advisor Position

**Verdict**: APPROVED. Scope is right-sized.

**Scope analysis**:

- Narrower would be: this ADR documents only the security agent's eval. That is too narrow because it fails the AC-6 contract that future agent authors apply the methodology without re-deriving it. The methodology must be generalized.
- Broader would be: this ADR documents an eval methodology for all agents including those with freeform output. That is too broad because the methodology demonstrably works only on deterministic-scorable output. The ADR's explicit scope statement ("deterministic-scorable agents only") prevents over-application.
- The ADR also wisely defers CI integration to a follow-up issue. Trying to bundle CI integration into this ADR would force decisions (cost-budget enforcement, gate-failure routing) that the spike has not yet earned the right to make.

**Strategic note**: The "scrap" outcome's archive-and-supersede consequence is what makes this ADR honest. Most "experimental methodology" ADRs in industry have no exit path; this one does.

## Round 2: Disagreements and Resolution

The only unresolved item from Round 1 was the critic's P1 concern about over-claiming on N=10. Resolution: the ADR's worked-example section explicitly states the verdict is "keep-as-audit," not "graduate-to-CI," precisely because the CI on the delta spans zero. The ADR also names the minimum detectable effect size (~0.30 for N=10) and instructs the reader that "no difference" cannot be claimed at this sample size. This satisfies the critic.

No other disagreements requiring resolution.

## Round 3: Consensus Position

All six perspectives converge on APPROVED, with the amendments described above already incorporated into the prepared ADR body.

**Consensus verdict**: ADR-058 is ready for ratification with the prepared content. No blocking issues. The two-step write (debate log first, ADR second) per ADR-033 is satisfied by this artifact.

**Sign-off**:

- Architect: APPROVED
- Critic: APPROVED with amendments incorporated
- Independent-thinker: APPROVED
- Security: APPROVED
- Analyst: APPROVED
- High-level-advisor: APPROVED

## Decision Trail

| Item | Outcome |
|---|---|
| ADR status on commit | `proposed` (decision per AC-6 of T4-7 follows in a separate ADR / verdict event; this ADR ratifies the methodology, not the spike's verdict) |
| Decision verdict on the spike itself | `keep-as-audit` per AC-5 (positive delta, CI spans zero, flakiness=true). The ADR records the verdict in the worked-example section. |
| Cross-reference to ADR-057 | Bidirectional in spirit. This ADR cites ADR-057 explicitly. ADR-057 update is a follow-up, out of scope. |
| File budget | 2 files (debate log + ADR). No other modifications. |
| Push policy | Do not push; user pushes. |
